<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Refresh, VideoPlay } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { api } from '@/api/client'
import type { Dashboard, Scan } from '@/types'

const dashboard = ref<Dashboard>()
const scanning = ref(false)
const lastScan = ref<Scan>()
const load = async () => { dashboard.value = await api.dashboard() }
const runScan = async () => {
  scanning.value = true
  try { lastScan.value = await api.scan(); await load(); if (lastScan.value.status === 'failed') ElMessage.warning(`扫描未完成：${lastScan.value.error}`); else ElMessage.success('扫描任务完成') }
  finally { scanning.value = false }
}
const priorityLabel = (value: string) => ({ high: '高优先级', medium: '中优先级', low: '低优先级' }[value] ?? value)
onMounted(load)
</script>

<template>
  <div class="dashboard" v-loading="!dashboard">
    <section class="hero"><div><span class="eyebrow">TODAY'S RELATIONSHIP PULSE</span><h2>把关心，放在恰好的时间。</h2><p>AI 已根据互动间隔与关系档案整理今日待关注的人。</p></div><el-button type="primary" size="large" :loading="scanning" @click="runScan"><el-icon><VideoPlay /></el-icon>立即扫描</el-button></section>
    <section class="metrics" v-if="dashboard"><article><span>今日需维护</span><strong>{{ dashboard.today_needing_attention }}</strong><small>位好友等待自然互动</small></article><article><span>高优先级关系</span><strong>{{ dashboard.high_priority_users.length }}</strong><small>需要更稳定地维系</small></article><article><span>待确认建议</span><strong>{{ dashboard.pending_suggestions }}</strong><small>不会自动发送</small></article></section>
    <section class="grid" v-if="dashboard"><div class="panel"><div class="panel-title"><h3>高优先级关系</h3><router-link to="/friends">查看全部</router-link></div><div class="friend-row" v-for="friend in dashboard.high_priority_users" :key="friend.id"><div class="avatar">{{ friend.nickname.slice(0, 1) }}</div><div><b>{{ friend.nickname }}</b><p>{{ friend.relationship }} · {{ friend.tags.join(' · ') || '未添加标签' }}</p></div><el-tag type="danger" size="small">{{ priorityLabel(friend.priority) }}</el-tag></div><el-empty v-if="!dashboard.high_priority_users.length" description="暂未设置高优先级关系" :image-size="72" /></div>
      <div class="panel"><div class="panel-title"><h3>最近互动</h3><el-button text :icon="Refresh" @click="load">刷新</el-button></div><div class="interaction" v-for="record in dashboard.recent_interactions" :key="record.id"><span class="timeline-dot"></span><div><b>{{ record.content || '已记录一次互动' }}</b><p>{{ new Date(record.time).toLocaleString() }} · {{ record.source === 'ocr' ? '视觉识别' : '手动记录' }}</p></div></div><el-empty v-if="!dashboard.recent_interactions.length" description="还没有互动记录" :image-size="72" /></div></section>
    <el-alert v-if="lastScan" :title="`最近扫描：${lastScan.status === 'completed' ? `匹配 ${lastScan.result_count} 位已建档好友` : '执行失败'}`" :type="lastScan.status === 'completed' ? 'success' : 'warning'" show-icon :closable="false" />
  </div>
</template>
