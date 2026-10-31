<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.subtitle') }}</p>
    </div>

    <div class="card budget-card">
      <div class="card-header">
        <h3 class="card-title">{{ t('restocking.budgetTitle') }}</h3>
        <div class="budget-amount" aria-live="polite">
          <span class="budget-amount-label">{{ t('restocking.budgetLabel') }}</span>
          <span class="budget-amount-value">{{ formatCurrency(budget, currentCurrency) }}</span>
        </div>
      </div>
      <input
        id="restocking-budget"
        v-model.number="budget"
        type="range"
        class="budget-slider"
        :min="BUDGET_MIN"
        :max="BUDGET_MAX"
        :step="BUDGET_STEP"
        :aria-label="t('restocking.budgetLabel')"
      />
      <div class="slider-labels">
        <span>{{ t('restocking.budgetMin') }}: {{ formatCurrency(BUDGET_MIN, currentCurrency) }}</span>
        <span>{{ t('restocking.budgetMax') }}: {{ formatCurrency(BUDGET_MAX, currentCurrency) }}</span>
      </div>
      <p class="budget-help">{{ t('restocking.budgetHelp') }}</p>
    </div>

    <div v-if="successOrder" class="success-banner" role="status">
      <span>{{ t('restocking.success', { orderNumber: successOrder.order_number }) }}</span>
      <router-link to="/orders" class="success-link">{{ t('restocking.viewInOrders') }}</router-link>
    </div>
    <div v-if="orderError" class="error" role="alert">{{ orderError }}</div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error && !recommendation" class="error">{{ error }}</div>
    <div v-else-if="recommendation">
      <div v-if="error" class="error">{{ error }}</div>

      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-label">{{ t('restocking.stats.itemsRecommended') }}</div>
          <div class="stat-value">{{ items.length }}</div>
        </div>
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.stats.totalCost') }}</div>
          <div class="stat-value">{{ formatCurrencyWithDecimals(recommendation.total_cost, currentCurrency, 2) }}</div>
        </div>
        <div class="stat-card success">
          <div class="stat-label">{{ t('restocking.stats.remainingBudget') }}</div>
          <div class="stat-value">{{ formatCurrencyWithDecimals(recommendation.remaining_budget, currentCurrency, 2) }}</div>
        </div>
        <div class="stat-card warning">
          <div class="stat-label">{{ t('restocking.stats.leadTime') }}</div>
          <div class="stat-value">{{ leadTimeLabel }}</div>
        </div>
      </div>

      <div class="card" :class="{ refreshing: isStale }">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommendations') }} ({{ items.length }})</h3>
          <div class="order-actions">
            <span v-if="isStale" class="status-note">{{ t('restocking.updating') }}</span>
            <button
              type="button"
              class="place-order-button"
              :disabled="!canPlaceOrder"
              @click="placeOrder"
            >
              {{ submitting ? t('restocking.placing') : t('restocking.placeOrder') }}
            </button>
          </div>
        </div>

        <div v-if="items.length === 0" class="empty-state">{{ t('restocking.empty') }}</div>
        <div v-else class="table-container">
          <table>
            <thead>
              <tr>
                <th>{{ t('restocking.table.sku') }}</th>
                <th>{{ t('restocking.table.itemName') }}</th>
                <th>{{ t('restocking.table.trend') }}</th>
                <th class="num">{{ t('restocking.table.forecastedDemand') }}</th>
                <th class="num">{{ t('restocking.table.onHand') }}</th>
                <th class="num">{{ t('restocking.table.recommendedQty') }}</th>
                <th class="num">{{ t('restocking.table.unitCost') }}</th>
                <th class="num">{{ t('restocking.table.lineTotal') }}</th>
                <th class="num">{{ t('restocking.table.leadTime') }}</th>
                <th>{{ t('restocking.table.supplier') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in items" :key="item.item_sku">
                <td class="nowrap"><strong>{{ item.item_sku }}</strong></td>
                <td>{{ translateProductName(item.item_name) }}</td>
                <td>
                  <span :class="['badge', item.trend]">{{ t(`trends.${item.trend}`) }}</span>
                </td>
                <td class="num">{{ item.forecasted_demand.toLocaleString() }}</td>
                <td class="num">{{ item.quantity_on_hand.toLocaleString() }}</td>
                <td class="num"><strong>{{ item.recommended_quantity.toLocaleString() }}</strong></td>
                <td class="num">{{ formatCurrencyWithDecimals(item.unit_cost, currentCurrency, 2) }}</td>
                <td class="num"><strong>{{ formatCurrencyWithDecimals(item.line_total, currentCurrency, 2) }}</strong></td>
                <td class="num">{{ t('restocking.leadTimeDays', { days: item.lead_time_days }) }}</td>
                <td>{{ item.supplier }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'
import { formatCurrency, formatCurrencyWithDecimals } from '../utils/currency'

// Slider range is always in USD; only the displayed amounts are converted for ja.
const BUDGET_MIN = 0
const BUDGET_MAX = 100000
const BUDGET_STEP = 1000
const DEBOUNCE_MS = 250

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency, translateProductName } = useI18n()

    // Note: the global FilterBar filters (period, warehouse, category, status) are
    // intentionally NOT watched here. The restocking forecast has no time or
    // warehouse dimension, so those filters would not change the recommendations.
    const budget = ref(25000)
    const recommendation = ref(null)
    const loading = ref(true) // only true until the first response arrives
    const fetching = ref(false) // a recommendation request is in flight
    const submitting = ref(false)
    const error = ref(null)
    const orderError = ref(null)
    const successOrder = ref(null)

    const items = computed(() => recommendation.value?.items ?? [])

    // The shown recommendation is stale while the slider has moved past the budget it
    // was computed for (debounce pending) or while a new request is in flight.
    const isStale = computed(() => {
      return fetching.value || !recommendation.value || recommendation.value.budget !== budget.value
    })

    const canPlaceOrder = computed(() => {
      return items.value.length > 0 && !submitting.value && !isStale.value
    })

    const leadTimeLabel = computed(() => {
      if (items.value.length === 0) return '-'
      return t('restocking.leadTimeDays', { days: recommendation.value.lead_time_days })
    })

    // Out-of-order guard: each request gets an increasing id and only the latest
    // request may write state, so a slow response for an old budget can never
    // overwrite the result of a newer slider position.
    let requestCounter = 0

    const loadRecommendations = async () => {
      const requestId = ++requestCounter
      fetching.value = true
      try {
        const data = await api.getRestockingRecommendations(budget.value)
        if (requestId !== requestCounter) return
        recommendation.value = data
        error.value = null
      } catch (err) {
        if (requestId !== requestCounter) return
        error.value = t('restocking.loadError')
        console.error('Failed to load restocking recommendations:', err)
      } finally {
        if (requestId === requestCounter) {
          fetching.value = false
          loading.value = false
        }
      }
    }

    // Debounce slider drags so we send one request once the user pauses (~250 ms)
    // instead of one per step. The initial load on mount skips the debounce.
    let debounceTimer = null
    watch(budget, () => {
      orderError.value = null
      clearTimeout(debounceTimer)
      debounceTimer = setTimeout(loadRecommendations, DEBOUNCE_MS)
    })

    const placeOrder = async () => {
      if (!canPlaceOrder.value) return
      submitting.value = true
      orderError.value = null
      successOrder.value = null

      // Post the budget the recommendation was computed for (not the live slider
      // value) so the server validates the quantities against the same budget.
      const payload = {
        budget: recommendation.value.budget,
        items: recommendation.value.items.map(item => ({
          item_sku: item.item_sku,
          quantity: item.recommended_quantity
        }))
      }

      try {
        successOrder.value = await api.createRestockingOrder(payload)
        // Refresh so the table reflects the server state after the order.
        await loadRecommendations()
      } catch (err) {
        // Keep the user's budget and recommendations so they can retry or adjust.
        orderError.value = err.response?.data?.detail || t('restocking.error')
        console.error('Failed to place restocking order:', err)
      } finally {
        submitting.value = false
      }
    }

    onMounted(loadRecommendations)

    onBeforeUnmount(() => {
      clearTimeout(debounceTimer)
      // Invalidate any in-flight request so it cannot write state after unmount.
      requestCounter++
    })

    return {
      t,
      currentCurrency,
      translateProductName,
      formatCurrency,
      formatCurrencyWithDecimals,
      BUDGET_MIN,
      BUDGET_MAX,
      BUDGET_STEP,
      budget,
      recommendation,
      items,
      loading,
      error,
      orderError,
      successOrder,
      submitting,
      isStale,
      canPlaceOrder,
      leadTimeLabel,
      placeOrder
    }
  }
}
</script>

<style scoped>
.budget-amount {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
}

.budget-amount-label {
  color: #64748b;
  font-size: 0.875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.budget-amount-value {
  font-size: 1.75rem;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.025em;
}

/* Slider: slate track, blue thumb (WebKit + Firefox) */
.budget-slider {
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  height: 8px;
  background: transparent;
  cursor: pointer;
  margin: 0.5rem 0;
}

.budget-slider:focus {
  outline: none;
}

.budget-slider::-webkit-slider-runnable-track {
  height: 8px;
  background: #cbd5e1;
  border-radius: 4px;
}

.budget-slider::-moz-range-track {
  height: 8px;
  background: #cbd5e1;
  border-radius: 4px;
}

.budget-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 22px;
  height: 22px;
  margin-top: -7px; /* centre the thumb on the 8px track */
  background: #2563eb;
  border: 3px solid white;
  border-radius: 50%;
  box-shadow: 0 1px 4px rgba(15, 23, 42, 0.35);
  transition: transform 0.15s ease;
}

.budget-slider::-moz-range-thumb {
  width: 16px;
  height: 16px;
  background: #2563eb;
  border: 3px solid white;
  border-radius: 50%;
  box-shadow: 0 1px 4px rgba(15, 23, 42, 0.35);
}

.budget-slider:hover::-webkit-slider-thumb {
  transform: scale(1.1);
}

.budget-slider:focus-visible::-webkit-slider-thumb {
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.35);
}

.budget-slider:focus-visible::-moz-range-thumb {
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.35);
}

.slider-labels {
  display: flex;
  justify-content: space-between;
  font-size: 0.813rem;
  color: #64748b;
}

.budget-help {
  margin-top: 0.75rem;
  font-size: 0.813rem;
  color: #64748b;
}

/* Success banner (the global .error style covers failures) */
.success-banner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  background: #ecfdf5;
  border: 1px solid #a7f3d0;
  color: #065f46;
  padding: 1rem;
  border-radius: 8px;
  margin: 1rem 0;
  font-size: 0.938rem;
  font-weight: 500;
}

.success-link {
  color: #047857;
  font-weight: 600;
  text-decoration: underline;
  white-space: nowrap;
}

.success-link:hover {
  color: #065f46;
}

.order-actions {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.status-note {
  font-size: 0.813rem;
  color: #64748b;
}

/* Dim the table while a newer recommendation is on its way */
.refreshing .table-container {
  opacity: 0.6;
  transition: opacity 0.15s ease;
}

.place-order-button {
  padding: 0.5rem 1.25rem;
  border: none;
  border-radius: 6px;
  background: #2563eb;
  color: white;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  white-space: nowrap;
}

.place-order-button:hover:not(:disabled) {
  background: #1d4ed8;
  transform: translateY(-1px);
  box-shadow: 0 2px 4px rgba(37, 99, 235, 0.3);
}

.place-order-button:disabled {
  background: #94a3b8;
  cursor: not-allowed;
}

.empty-state {
  text-align: center;
  padding: 2.5rem 1rem;
  color: #64748b;
  font-size: 0.938rem;
}

/* Four stat cards fit on one row at typical desktop widths */
.stats-grid {
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}

/* Ten columns: tighter cell padding so the table fits the content column
   without a horizontal scrollbar at ~1440px */
th,
td {
  padding-left: 0.5rem;
  padding-right: 0.5rem;
}

th.num,
td.num {
  text-align: right;
  white-space: nowrap;
}

/* Keep SKUs on one line (they contain a hyphen and would otherwise wrap) */
td.nowrap {
  white-space: nowrap;
}
</style>
