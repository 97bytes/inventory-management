<template>
  <div class="app">
    <!-- Backdrop for the off-canvas sidebar on narrow screens -->
    <div v-if="navOpen" class="sidebar-backdrop" @click="navOpen = false"></div>

    <aside class="sidebar" :class="{ open: navOpen }">
      <div class="brand">
        <div class="brand-text">
          <h1>{{ t('nav.companyName') }}</h1>
          <span class="subtitle">{{ t('nav.subtitle') }}</span>
        </div>
      </div>

      <nav class="sidebar-nav" :aria-label="t('nav.primary')">
        <router-link
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          class="nav-link"
          :class="{ active: $route.path === item.to }"
          @click="navOpen = false"
        >
          <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path v-for="d in item.icon" :key="d" :d="d" />
          </svg>
          <span class="nav-label">{{ item.label }}</span>
        </router-link>
      </nav>
    </aside>

    <div class="app-main">
      <header class="topbar">
        <button
          type="button"
          class="menu-button"
          :aria-label="t('nav.menu')"
          :aria-expanded="navOpen"
          @click="navOpen = !navOpen"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" aria-hidden="true">
            <path d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>
        <FilterBar />
        <div class="topbar-actions">
          <LanguageSwitcher />
          <ProfileMenu
            @show-profile-details="showProfileDetails = true"
            @show-tasks="showTasks = true"
          />
        </div>
      </header>
      <main class="main-content">
        <router-view />
      </main>
    </div>

    <ProfileDetailsModal
      :is-open="showProfileDetails"
      @close="showProfileDetails = false"
    />

    <TasksModal
      :is-open="showTasks"
      :tasks="tasks"
      @close="showTasks = false"
      @add-task="addTask"
      @delete-task="deleteTask"
      @toggle-task="toggleTask"
    />
  </div>
</template>

<script>
import { ref, onMounted, computed } from 'vue'
import { api } from './api'
import { useAuth } from './composables/useAuth'
import { useI18n } from './composables/useI18n'
import FilterBar from './components/FilterBar.vue'
import ProfileMenu from './components/ProfileMenu.vue'
import ProfileDetailsModal from './components/ProfileDetailsModal.vue'
import TasksModal from './components/TasksModal.vue'
import LanguageSwitcher from './components/LanguageSwitcher.vue'

export default {
  name: 'App',
  components: {
    FilterBar,
    ProfileMenu,
    ProfileDetailsModal,
    TasksModal,
    LanguageSwitcher
  },
  setup() {
    const { currentUser } = useAuth()
    const { t } = useI18n()
    const showProfileDetails = ref(false)
    const showTasks = ref(false)
    const apiTasks = ref([])
    // Off-canvas sidebar state (only used below 900px)
    const navOpen = ref(false)

    // Line icons (24x24 grid, stroke only). Each icon is a list of path data strings.
    // Reports label is intentionally a literal: there is no nav.reports key.
    const navItems = computed(() => [
      { to: '/', label: t('nav.overview'), icon: ['M3 3h7v9H3z', 'M14 3h7v5h-7z', 'M14 12h7v9h-7z', 'M3 16h7v5H3z'] },
      { to: '/inventory', label: t('nav.inventory'), icon: ['M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z', 'M3.3 7 12 12l8.7-5', 'M12 22V12'] },
      { to: '/orders', label: t('nav.orders'), icon: ['M9 2h6a1 1 0 0 1 1 1v2a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1z', 'M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2', 'M9 12h6', 'M9 16h4'] },
      { to: '/spending', label: t('nav.finance'), icon: ['M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z', 'M15 9.5c-.5-1-1.5-1.5-3-1.5-1.7 0-3 .8-3 2s1.3 1.7 3 2 3 .8 3 2-1.3 2-3 2c-1.5 0-2.5-.5-3-1.5', 'M12 6v2', 'M12 16v2'] },
      { to: '/demand', label: t('nav.demandForecast'), icon: ['M22 7l-8.5 8.5-5-5L2 17', 'M16 7h6v6'] },
      { to: '/restocking', label: t('nav.restocking'), icon: ['M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8', 'M21 3v5h-5'] },
      { to: '/reports', label: 'Reports', icon: ['M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z', 'M14 2v6h6', 'M8 13h8', 'M8 17h8', 'M8 9h2'] }
    ])

    // Merge mock tasks from currentUser with API tasks
    const tasks = computed(() => {
      return [...currentUser.value.tasks, ...apiTasks.value]
    })

    const loadTasks = async () => {
      try {
        apiTasks.value = await api.getTasks()
      } catch (err) {
        console.error('Failed to load tasks:', err)
      }
    }

    const addTask = async (taskData) => {
      try {
        const newTask = await api.createTask(taskData)
        // Add new task to the beginning of the array
        apiTasks.value.unshift(newTask)
      } catch (err) {
        console.error('Failed to add task:', err)
      }
    }

    const deleteTask = async (taskId) => {
      try {
        // Check if it's a mock task (from currentUser)
        const isMockTask = currentUser.value.tasks.some(t => t.id === taskId)

        if (isMockTask) {
          // Remove from mock tasks
          const index = currentUser.value.tasks.findIndex(t => t.id === taskId)
          if (index !== -1) {
            currentUser.value.tasks.splice(index, 1)
          }
        } else {
          // Remove from API tasks
          await api.deleteTask(taskId)
          apiTasks.value = apiTasks.value.filter(t => t.id !== taskId)
        }
      } catch (err) {
        console.error('Failed to delete task:', err)
      }
    }

    const toggleTask = async (taskId) => {
      try {
        // Check if it's a mock task (from currentUser)
        const mockTask = currentUser.value.tasks.find(t => t.id === taskId)

        if (mockTask) {
          // Toggle mock task status
          mockTask.status = mockTask.status === 'pending' ? 'completed' : 'pending'
        } else {
          // Toggle API task
          const updatedTask = await api.toggleTask(taskId)
          const index = apiTasks.value.findIndex(t => t.id === taskId)
          if (index !== -1) {
            apiTasks.value[index] = updatedTask
          }
        }
      } catch (err) {
        console.error('Failed to toggle task:', err)
      }
    }

    onMounted(loadTasks)

    return {
      t,
      navOpen,
      navItems,
      showProfileDetails,
      showTasks,
      tasks,
      addTask,
      deleteTask,
      toggleTask
    }
  }
}
</script>

<style>
/* Design tokens: slate palette, blue accent, unchanged status colours */
:root {
  --color-text: #0f172a;
  --color-text-body: #334155;
  --color-muted: #64748b;
  --color-border: #e2e8f0;
  --color-border-strong: #cbd5e1;
  --color-surface: #ffffff;
  --color-surface-alt: #f8fafc;
  --color-surface-muted: #f1f5f9;
  --color-page: #f1f5f9;
  --color-accent: #2563eb;
  --color-accent-hover: #1d4ed8;
  --color-accent-soft: #eff6ff;

  --space-1: 0.25rem;
  --space-2: 0.5rem;
  --space-3: 0.75rem;
  --space-4: 1rem;
  --space-5: 1.25rem;
  --space-6: 1.5rem;
  --space-8: 2rem;

  --radius-sm: 6px;
  --radius-md: 8px;
  --radius-lg: 12px;

  --shadow-sm: 0 1px 2px rgba(15, 23, 42, 0.04);
  --shadow-md: 0 4px 12px rgba(15, 23, 42, 0.07);
  --focus-ring: 0 0 0 3px rgba(37, 99, 235, 0.25);

  --sidebar-width: 240px;
  --topbar-height: 64px;
  --transition: 150ms ease;
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
  background: var(--color-page);
  color: var(--color-text-body);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* Visible keyboard focus everywhere; mouse clicks do not show the ring */
:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

button,
select,
input {
  font-family: inherit;
}

/* ---------- Shell ---------- */

.app {
  min-height: 100vh;
}

/* Sidebar is fixed (not sticky) so it never scrolls with the page content.
   z-index 100 keeps it under the modals (1000-2000) but over page content. */
.sidebar {
  position: fixed;
  top: 0;
  left: 0;
  bottom: 0;
  width: var(--sidebar-width);
  display: flex;
  flex-direction: column;
  background: var(--color-surface);
  border-right: 1px solid var(--color-border);
  z-index: 100;
  overflow-y: auto;
}

.brand {
  display: flex;
  align-items: center;
  /* Same height as the topbar so the two bottom borders line up */
  min-height: var(--topbar-height);
  padding: 0 var(--space-5);
  border-bottom: 1px solid var(--color-border);
}

.brand-text {
  min-width: 0;
}

.brand-text h1 {
  font-size: 1rem;
  font-weight: 700;
  line-height: 1.25;
  color: var(--color-text);
  letter-spacing: -0.01em;
}

.subtitle {
  display: block;
  margin-top: 2px;
  font-size: 0.75rem;
  line-height: 1.3;
  color: var(--color-muted);
}

.sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-4) var(--space-3);
}

.nav-link {
  position: relative;
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: 0.625rem var(--space-3);
  border-radius: var(--radius-md);
  color: var(--color-muted);
  text-decoration: none;
  font-size: 0.875rem;
  font-weight: 500;
  transition: color var(--transition), background-color var(--transition);
}

.nav-icon {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
}

.nav-label {
  min-width: 0;
  overflow-wrap: anywhere;
}

.nav-link:hover {
  color: var(--color-text);
  background: var(--color-surface-muted);
}

.nav-link.active {
  color: var(--color-accent);
  background: var(--color-accent-soft);
  font-weight: 600;
}

/* Accent bar on the active item */
.nav-link.active::before {
  content: '';
  position: absolute;
  left: calc(-1 * var(--space-3));
  top: 8px;
  bottom: 8px;
  width: 3px;
  border-radius: 0 3px 3px 0;
  background: var(--color-accent);
}

/* min-width: 0 lets wide tables/charts scroll inside the content column
   instead of stretching the whole page past the viewport. */
.app-main {
  margin-left: var(--sidebar-width);
  min-width: 0;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

/* z-index 90 sits below the sidebar (100) but above page content; header dropdowns
   (z-index 1000) live inside this stacking context, so they must not be clipped:
   never add overflow: hidden here. */
.topbar {
  position: sticky;
  top: 0;
  z-index: 90;
  display: flex;
  align-items: center;
  gap: var(--space-4);
  min-height: var(--topbar-height);
  padding: var(--space-2) var(--space-8);
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
  box-shadow: var(--shadow-sm);
}

.topbar-actions {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-left: auto;
  flex-shrink: 0;
}

.menu-button {
  display: none;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  flex-shrink: 0;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-text-body);
  cursor: pointer;
  transition: background-color var(--transition), border-color var(--transition);
}

.menu-button:hover {
  background: var(--color-surface-alt);
  border-color: var(--color-border-strong);
}

.menu-button svg {
  width: 20px;
  height: 20px;
}

.sidebar-backdrop {
  display: none;
}

.main-content {
  flex: 1;
  width: 100%;
  max-width: 1600px;
  margin: 0 auto;
  padding: var(--space-6) var(--space-8) var(--space-8);
}

/* Narrow screens: sidebar becomes an off-canvas drawer opened by the menu button */
@media (max-width: 900px) {
  .sidebar {
    transform: translateX(-100%);
    transition: transform 200ms ease;
    box-shadow: none;
  }

  .sidebar.open {
    transform: translateX(0);
    box-shadow: 0 10px 25px rgba(15, 23, 42, 0.2);
  }

  .sidebar-backdrop {
    display: block;
    position: fixed;
    inset: 0;
    z-index: 95;
    background: rgba(15, 23, 42, 0.4);
  }

  .app-main {
    margin-left: 0;
  }

  .menu-button {
    display: inline-flex;
  }

  /* The wrapped filters make the bar tall; let it scroll away instead of eating the viewport */
  .topbar {
    position: static;
    flex-wrap: wrap;
    padding: var(--space-2) var(--space-4);
  }

  .main-content {
    padding: var(--space-4);
  }
}

/* ---------- Page header ---------- */

.page-header {
  margin-bottom: var(--space-6);
}

.page-header h2 {
  font-size: 1.5rem;
  font-weight: 700;
  line-height: 1.3;
  color: var(--color-text);
  margin-bottom: var(--space-1);
  letter-spacing: -0.02em;
}

.page-header p {
  color: var(--color-muted);
  font-size: 0.875rem;
}

/* ---------- Stat cards ---------- */

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: var(--space-4);
  margin-bottom: var(--space-6);
}

.stat-card {
  background: var(--color-surface);
  padding: var(--space-5);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border);
  box-shadow: var(--shadow-sm);
  transition: border-color var(--transition), box-shadow var(--transition);
}

.stat-card:hover {
  border-color: var(--color-border-strong);
  box-shadow: var(--shadow-md);
}

.stat-label {
  color: var(--color-muted);
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: var(--space-2);
}

.stat-value {
  font-size: 1.875rem;
  font-weight: 700;
  line-height: 1.2;
  color: var(--color-text);
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
}

.stat-card.warning .stat-value {
  color: #ea580c;
}

.stat-card.success .stat-value {
  color: #059669;
}

.stat-card.danger .stat-value {
  color: #dc2626;
}

.stat-card.info .stat-value {
  color: #2563eb;
}

/* ---------- Cards ---------- */

.card {
  background: var(--color-surface);
  border-radius: var(--radius-lg);
  padding: var(--space-5) var(--space-6);
  border: 1px solid var(--color-border);
  box-shadow: var(--shadow-sm);
  margin-bottom: var(--space-5);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-4);
  margin-bottom: var(--space-4);
  padding-bottom: var(--space-4);
  border-bottom: 1px solid var(--color-border);
}

.card-title {
  font-size: 1rem;
  font-weight: 600;
  color: var(--color-text);
  letter-spacing: -0.01em;
}

/* ---------- Tables ---------- */

.table-container {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
}

thead {
  background: var(--color-surface-alt);
}

th {
  text-align: left;
  padding: 0.75rem var(--space-3);
  font-weight: 600;
  color: var(--color-muted);
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  background: var(--color-surface-alt);
  border-top: 1px solid var(--color-border);
  border-bottom: 1px solid var(--color-border);
}

td {
  padding: 0.875rem var(--space-3);
  border-top: 1px solid var(--color-surface-muted);
  color: var(--color-text-body);
  font-size: 0.875rem;
  font-variant-numeric: tabular-nums;
}

tbody tr {
  transition: background-color var(--transition);
}

tbody tr:hover {
  background: var(--color-surface-alt);
}

/* ---------- Badges ---------- */

.badge {
  display: inline-block;
  padding: 0.25rem 0.625rem;
  border-radius: 999px;
  font-size: 0.688rem;
  font-weight: 600;
  line-height: 1.3;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  white-space: nowrap;
}

.badge.success {
  background: #d1fae5;
  color: #065f46;
}

.badge.warning {
  background: #fed7aa;
  color: #92400e;
}

.badge.danger {
  background: #fecaca;
  color: #991b1b;
}

.badge.info {
  background: #dbeafe;
  color: #1e40af;
}

.badge.increasing {
  background: #d1fae5;
  color: #065f46;
}

.badge.decreasing {
  background: #fecaca;
  color: #991b1b;
}

.badge.stable {
  background: #e0e7ff;
  color: #3730a3;
}

.badge.high {
  background: #fecaca;
  color: #991b1b;
}

.badge.medium {
  background: #fed7aa;
  color: #92400e;
}

.badge.low {
  background: #dbeafe;
  color: #1e40af;
}

/* ---------- States ---------- */

.loading {
  text-align: center;
  padding: 3rem;
  color: var(--color-muted);
  font-size: 0.938rem;
}

.error {
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #991b1b;
  padding: var(--space-4);
  border-radius: var(--radius-md);
  margin: var(--space-4) 0;
  font-size: 0.875rem;
}
</style>
