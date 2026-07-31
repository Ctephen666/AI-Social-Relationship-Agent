<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Check, CopyDocument, Delete } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { api } from '@/api/client'
import type { Suggestion } from '@/types'

const suggestions = ref<Suggestion[]>([]); const loading = ref(true)
const load = async () => { loading.value = true; try { suggestions.value = await api.suggestions() } finally { loading.value = false } }
const mark = async (item: Suggestion, status: 'copied' | 'dismissed' | 'used') => { if (status === 'copied') await navigator.clipboard.writeText(item.content); await api.updateSuggestion(item.id, status); await load(); ElMessage.success(status === 'copied' ? '话术已复制，发送前请自行确认内容' : '状态已更新') }
onMounted(load)
</script>

<template>
  <div><section class="toolbar"><div><h2>AI 建议中心</h2><p>所有内容均为草稿。系统不会代替你输入或发送消息。</p></div><el-tag type="success" effect="light">人工确认模式</el-tag></section><div class="suggestion-grid" v-loading="loading"><article v-for="item in suggestions" :key="item.id" class="suggestion-card"><div class="suggestion-head"><div class="name-cell"><span class="avatar small">{{ item.nickname?.slice(0, 1) }}</span><div><b>{{ item.nickname || '未知好友' }}</b><p>{{ new Date(item.created_at).toLocaleString() }}</p></div></div><el-tag :type="item.status === 'pending' ? 'warning' : 'info'">{{ item.status === 'pending' ? '待确认' : item.status }}</el-tag></div><blockquote>“{{ item.content }}”</blockquote><div class="reason"><span>推荐原因</span><p>{{ item.reason }}</p><small>语气：{{ item.tone }} · 风险：{{ item.risk_level }}</small></div><div class="suggestion-actions"><el-button v-if="item.status === 'pending'" :icon="CopyDocument" type="primary" @click="mark(item, 'copied')">复制建议</el-button><el-button v-if="item.status === 'pending'" :icon="Check" @click="mark(item, 'used')">标记已使用</el-button><el-button v-if="item.status === 'pending'" :icon="Delete" text type="danger" @click="mark(item, 'dismissed')">忽略</el-button></div></article><el-empty v-if="!loading && !suggestions.length" description="暂无 AI 建议。添加好友并扫描聊天列表后，建议会出现在这里。" /></div></div>
</template>
