<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { Calendar, Connection, Setting, UserFilled } from '@element-plus/icons-vue'

const route = useRoute()
const title = computed(() => route.meta.title ?? '关系概览')
const menus = [
  { path: '/', label: '关系概览', icon: Connection },
  { path: '/friends', label: '好友管理', icon: UserFilled },
  { path: '/suggestions', label: 'AI 建议', icon: Calendar },
  { path: '/settings', label: '设置', icon: Setting },
]
</script>

<template>
  <el-container class="shell">
    <el-aside width="244px" class="aside">
      <div class="brand"><span class="brand-dot">✦</span><div>RelationOS<small>AI Relationship Agent</small></div></div>
      <el-menu router :default-active="$route.path" class="menu">
        <el-menu-item v-for="item in menus" :key="item.path" :index="item.path"><el-icon><component :is="item.icon" /></el-icon>{{ item.label }}</el-menu-item>
      </el-menu>
      <div class="safety"><b>安全辅助模式</b><span>建议始终由你确认</span></div>
    </el-aside>
    <el-container>
      <el-header class="header"><div><h1>{{ title }}</h1><p>本地优先 · 人工确认 · 不自动发送</p></div><el-tag type="success" effect="dark" round>Agent 在线</el-tag></el-header>
      <el-main class="main"><router-view /></el-main>
    </el-container>
  </el-container>
</template>

