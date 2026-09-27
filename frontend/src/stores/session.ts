import { defineStore } from 'pinia'

export type ShiftRole = '处置人员' | '值班长'

export const useSessionStore = defineStore('session', {
  state: () => ({
    operator: '值班管理员',
    role: '处置人员' as ShiftRole,
    shiftLabel: '白班 08:00-20:00',
    scope: '污水处理厂工艺管理平台',
  }),
  getters: {
    canOperate: (state) => state.operator.length > 0,
    isShiftLeader: (state) => state.role === '值班长',
  },
  actions: {
    setShift(label: string) {
      this.shiftLabel = label
    },
    setRole(role: ShiftRole) {
      this.role = role
    },
  },
})
