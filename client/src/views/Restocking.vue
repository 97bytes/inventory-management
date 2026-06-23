<template>
  <div class="restocking">
    <!-- Page header -->
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>

      <!-- Success banner (shown after order placed) -->
      <div v-if="successOrder" class="success-banner">
        <strong>{{ t('restocking.successTitle') }}</strong>
        <p>{{ t('restocking.successMessage', { orderNumber: successOrder.order_number }) }}</p>
        <router-link to="/orders">{{ t('restocking.viewOrders') }}</router-link>
      </div>

      <!-- Budget card -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.budgetLabel') }}</h3>
          <span class="budget-value">{{ currencySymbol }}{{ budget.toLocaleString() }}</span>
        </div>
        <!-- v-model.number keeps budget as a Number, not a String -->
        <input
          type="range"
          min="0"
          max="50000"
          step="500"
          v-model.number="budget"
          class="budget-slider"
        />
        <div class="budget-meta">
          <span>{{ t('restocking.allocated') }}: {{ currencySymbol }}{{ allocated.toLocaleString(undefined, { maximumFractionDigits: 0 }) }}</span>
          <span>{{ t('restocking.remaining') }}: {{ currencySymbol }}{{ budgetRemaining.toLocaleString(undefined, { maximumFractionDigits: 0 }) }}</span>
        </div>
      </div>

      <!-- Recommendations card -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommendations') }} ({{ recommendations.length }})</h3>
        </div>

        <div v-if="recommendations.length === 0" class="loading">
          {{ t('restocking.noRecommendations') }}
        </div>
        <div v-else class="table-container">
          <table>
            <thead>
              <tr>
                <th>{{ t('restocking.table.sku') }}</th>
                <th>{{ t('restocking.table.itemName') }}</th>
                <th>{{ t('restocking.table.category') }}</th>
                <th>{{ t('restocking.table.forecastedDemand') }}</th>
                <th>{{ t('restocking.table.unitCost') }}</th>
                <th>{{ t('restocking.table.quantity') }}</th>
                <th>{{ t('restocking.table.subtotal') }}</th>
                <th>{{ t('restocking.table.leadTime') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in recommendations" :key="item.item_sku">
                <td><strong>{{ item.item_sku }}</strong></td>
                <td>{{ item.item_name }}</td>
                <td>{{ item.category }}</td>
                <td>{{ item.forecasted_demand.toLocaleString() }}</td>
                <td>{{ currencySymbol }}{{ item.unit_cost.toFixed(2) }}</td>
                <td>{{ item.quantity_to_order.toLocaleString() }}</td>
                <td><strong>{{ currencySymbol }}{{ item.subtotal.toLocaleString(undefined, { maximumFractionDigits: 0 }) }}</strong></td>
                <td><span class="badge info">{{ t('restocking.leadTimeDays', { days: item.lead_time_days }) }}</span></td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="card-footer">
          <button
            class="btn-primary"
            :disabled="recommendations.length === 0 || submitting"
            @click="placeOrder"
          >
            {{ submitting ? t('common.loading') : t('restocking.placeOrder') }}
          </button>
        </div>
      </div>

    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'

// Lead time (days) by 3-letter SKU prefix
const LEAD_TIME_MAP = {
  WDG: 7, BRG: 14, GSK: 10, MTR: 21,
  FLT: 5, VLV: 12, PSU: 10, SNR: 10, CTL: 14
}

// Derive lead time from the first segment of a hyphenated SKU (e.g. "WDG-001" → "WDG")
function getLeadTime(sku) {
  return LEAD_TIME_MAP[sku.split('-')[0]] ?? 10
}

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency } = useI18n()

    // Show ¥ for JPY, $ for everything else
    const currencySymbol = computed(() => currentCurrency.value === 'JPY' ? '¥' : '$')

    const loading = ref(true)
    const error = ref(null)
    const forecasts = ref([])     // raw demand forecast records from API
    const budget = ref(10000)     // bound to range slider with v-model.number
    const submitting = ref(false)
    const successOrder = ref(null)

    // Greedy allocation: sort by highest forecasted demand, fill as many units as
    // the remaining budget allows, capping each item at its forecasted demand qty.
    const recommendations = computed(() => {
      const sorted = [...forecasts.value].sort(
        (a, b) => b.forecasted_demand - a.forecasted_demand
      )
      const result = []
      let remaining = budget.value
      for (const item of sorted) {
        if (remaining <= 0) break
        const maxAffordable = Math.floor(remaining / item.unit_cost)
        if (maxAffordable <= 0) continue
        const qty = Math.min(item.forecasted_demand, maxAffordable)
        const subtotal = qty * item.unit_cost
        result.push({
          ...item,
          quantity_to_order: qty,
          subtotal,
          lead_time_days: getLeadTime(item.item_sku)
        })
        remaining -= subtotal
      }
      return result
    })

    // Total cost of all recommended items
    const allocated = computed(() =>
      recommendations.value.reduce((sum, item) => sum + item.subtotal, 0)
    )

    // How much of the budget is left after allocation
    const budgetRemaining = computed(() => budget.value - allocated.value)

    onMounted(async () => {
      try {
        loading.value = true
        forecasts.value = await api.getDemandForecasts()
      } catch (err) {
        error.value = 'Failed to load demand forecasts: ' + err.message
      } finally {
        loading.value = false
      }
    })

    const placeOrder = async () => {
      if (recommendations.value.length === 0 || submitting.value) return
      submitting.value = true
      successOrder.value = null
      error.value = null
      try {
        const orderData = {
          budget: budget.value,
          items: recommendations.value.map(item => ({
            sku: item.item_sku,
            name: item.item_name,
            quantity: item.quantity_to_order,
            unit_price: item.unit_cost,
            lead_time_days: item.lead_time_days
          }))
        }
        const created = await api.createRestockingOrder(orderData)
        successOrder.value = created
        budget.value = 10000  // reset slider so user can start a fresh plan
      } catch (err) {
        error.value = 'Failed to submit order: ' + err.message
      } finally {
        submitting.value = false
      }
    }

    return {
      t,
      currencySymbol,
      loading,
      error,
      forecasts,
      budget,
      submitting,
      successOrder,
      recommendations,
      allocated,
      budgetRemaining,
      placeOrder
    }
  }
}
</script>

<style scoped>
.budget-slider {
  width: 100%;
  margin: 1rem 0 0.5rem;
  accent-color: #2563eb;
  height: 6px;
  cursor: pointer;
}

.budget-value {
  font-size: 1.75rem;
  font-weight: 700;
  color: #2563eb;
  letter-spacing: -0.03em;
}

.budget-meta {
  display: flex;
  justify-content: space-between;
  font-size: 0.875rem;
  color: #64748b;
  margin-top: 0.25rem;
}

.card-footer {
  padding-top: 1rem;
  border-top: 1px solid #e2e8f0;
  margin-top: 1rem;
  display: flex;
  justify-content: flex-end;
}

.btn-primary {
  background: #2563eb;
  color: white;
  border: none;
  padding: 0.625rem 1.5rem;
  border-radius: 6px;
  font-weight: 600;
  font-size: 0.938rem;
  cursor: pointer;
  transition: background 0.2s ease;
}

.btn-primary:hover:not(:disabled) {
  background: #1d4ed8;
}

.btn-primary:disabled {
  background: #94a3b8;
  cursor: not-allowed;
}

.success-banner {
  background: #d1fae5;
  border: 1px solid #6ee7b7;
  border-radius: 10px;
  padding: 1.25rem 1.5rem;
  margin-bottom: 1.25rem;
  color: #065f46;
}

.success-banner strong {
  display: block;
  font-size: 1rem;
  margin-bottom: 0.25rem;
}

.success-banner p {
  font-size: 0.875rem;
  margin-bottom: 0.5rem;
}

.success-banner a {
  color: #059669;
  font-weight: 600;
  text-decoration: underline;
  font-size: 0.875rem;
}
</style>
