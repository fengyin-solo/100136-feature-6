<template>
  <div class="app-shell">
    <aside class="app-side">
      <h1 class="app-title">污水处理厂工艺管理平台</h1>
      <nav class="nav-list">
        <RouterLink v-for="item in navItems" :key="item.path" :to="item.path" class="nav-item">
          {{ item.label }}
        </RouterLink>
      </nav>
    </aside>
    <main class="app-main">
      <header class="app-head">
        <span class="head-desc">面向污水处理厂进水调度、工艺运行、加药优化、污泥脱水、出水监控与药剂耗材的工艺管理后台。</span>
        <span class="head-user">
          当前值班：{{ store.operator }} · {{ store.shiftLabel }}
          <label class="role-switch">
            角色
            <select :value="store.role" @change="onRoleChange">
              <option value="值班员">值班员</option>
              <option value="值班长">值班长</option>
            </select>
          </label>
        </span>
      </header>
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
import { useSessionStore } from '@/stores/session'

const store = useSessionStore()

function onRoleChange(event: Event) {
  store.setRole((event.target as HTMLSelectElement).value as '值班员' | '值班长')
}

const navItems = [{ label: "运营概览", path: "/" }, { label: "厂站信息", path: "/plank" }, { label: "进水监控", path: "/inflow" }, { label: "曝气控制", path: "/aeration" }, { label: "加药管理", path: "/chemical" }, { label: "沉淀池管理", path: "/sediment" }, { label: "污泥脱水", path: "/sludge" }, { label: "出水监测", path: "/effluent" }, { label: "化验分析", path: "/labtest" }, { label: "化验药剂", path: "/reagent" }, { label: "设备维保", path: "/equip" }, { label: "泵站运行", path: "/pump" }, { label: "能耗管理", path: "/power" }, { label: "管网巡查", path: "/pipe" }, { label: "提升泵站", path: "/lift" }, { label: "仪表校准", path: "/meter" }, { label: "水量调度", path: "/dispatch2" }, { label: "雨污调控", path: "/storm" }, { label: "污染源溯源", path: "/pollutant" }, { label: "药剂耗材", path: "/material" }, { label: "排污许可", path: "/license" }]
</script>
