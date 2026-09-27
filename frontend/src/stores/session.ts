import { defineStore } from 'pinia'

export const useSessionStore = defineStore('session', {
  state: () => ({
    operator: '值班管理员',
    role: '值班员' as '值班员' | '值班长',
    shiftLabel: '白班 08:00-20:00',
    scope: '污水处理厂工艺管理平台',
  }),
  getters: {
    canOperate: (state) => state.operator.length > 0,
    isShiftLead: (state) => state.role === '值班长',
  },
  actions: {
    setShift(label: string) {
      this.shiftLabel = label
    },
    setRole(role: '值班员' | '值班长') {
      this.role = role
    },
  },
})
