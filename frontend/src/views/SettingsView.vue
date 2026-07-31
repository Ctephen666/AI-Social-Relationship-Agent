<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/api/client'
import type { Settings } from '@/types'

const form = reactive<Settings>({ scan_time: '09:00', scan_frequency: 'daily', ocr_region: null, keep_screenshots: false, llm_configured: false })
const regionText = ref('')
const load = async () => { const data = await api.settings(); Object.assign(form, data); regionText.value = data.ocr_region?.join(', ') ?? '' }
const save = async () => { const values = regionText.value.trim() ? regionText.value.split(/[,，]/).map(Number) : null; if (values && (values.length !== 4 || values.some(Number.isNaN))) return ElMessage.warning('OCR 区域请填写四个数字：left, top, width, height'); const data = await api.updateSettings({ scan_time: form.scan_time, scan_frequency: form.scan_frequency, ocr_region: values, keep_screenshots: form.keep_screenshots }); Object.assign(form, data); ElMessage.success('本地设置已保存') }
onMounted(load)
</script>

<template>
  <div class="settings-page"><section class="toolbar"><div><h2>工作台设置</h2><p>这些配置只保存在本地数据库；模型密钥通过后端 `.env` 管理。</p></div></section><el-form label-position="top" class="settings-form"><div class="panel"><h3>扫描计划</h3><div class="form-row"><el-form-item label="每日扫描时间"><el-time-picker v-model="form.scan_time" value-format="HH:mm" format="HH:mm" placeholder="09:00" /></el-form-item><el-form-item label="扫描频率"><el-select v-model="form.scan_frequency"><el-option value="daily" label="每天"/><el-option value="manual" label="仅手动"/></el-select></el-form-item></div><el-form-item label="OCR 截图区域"><el-input v-model="regionText" placeholder="left, top, width, height；留空则截取主屏幕"/><div class="field-tip">坐标单位为屏幕像素。建议只框选聊天列表，提升识别准确度。</div></el-form-item><el-form-item><el-switch v-model="form.keep_screenshots" active-text="保留原始截图"/><div class="field-tip">关闭后系统在 OCR 完成时删除截图，仅保存结构化识别结果。</div></el-form-item></div><div class="panel"><h3>模型与安全</h3><el-descriptions :column="1" border><el-descriptions-item label="模型连接"><el-tag :type="form.llm_configured ? 'success' : 'info'">{{ form.llm_configured ? '已通过 .env 配置' : '未配置，使用本地安全兜底话术' }}</el-tag></el-descriptions-item><el-descriptions-item label="发送权限"><el-tag type="success">禁用：仅生成建议</el-tag></el-descriptions-item><el-descriptions-item label="未来自动化"><span class="muted">当前版本拒绝鼠标、键盘和发送操作。</span></el-descriptions-item></el-descriptions></div><el-button type="primary" size="large" @click="save">保存设置</el-button></el-form></div>
</template>
