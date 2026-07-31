import { createRouter, createWebHistory } from 'vue-router'
import DashboardView from '@/views/DashboardView.vue'
import FriendsView from '@/views/FriendsView.vue'
import SuggestionsView from '@/views/SuggestionsView.vue'
import SettingsView from '@/views/SettingsView.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: DashboardView, meta: { title: '关系概览' } },
    { path: '/friends', component: FriendsView, meta: { title: '好友管理' } },
    { path: '/suggestions', component: SuggestionsView, meta: { title: 'AI 建议中心' } },
    { path: '/settings', component: SettingsView, meta: { title: '工作台设置' } },
  ],
})

