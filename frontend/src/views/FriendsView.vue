<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { Delete, Edit, Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/api/client'
import type { Priority, User } from '@/types'

const users = ref<User[]>([]); const dialog = ref(false); const editing = ref<User | null>(null)
const form = reactive({ nickname: '', relationship: '朋友', priority: 'medium' as Priority, tagsText: '' })
const load = async () => { users.value = await api.users() }
const open = (item?: User) => { editing.value = item ?? null; Object.assign(form, item ? { nickname: item.nickname, relationship: item.relationship, priority: item.priority, tagsText: item.tags.join(', ') } : { nickname: '', relationship: '朋友', priority: 'medium', tagsText: '' }); dialog.value = true }
const save = async () => { const payload = { nickname: form.nickname, relationship: form.relationship, priority: form.priority, tags: form.tagsText.split(/[,，]/).map(v => v.trim()).filter(Boolean) }; if (editing.value) await api.updateUser(editing.value.id, payload); else await api.createUser(payload); dialog.value = false; await load(); ElMessage.success('好友档案已保存') }
const remove = async (item: User) => { await ElMessageBox.confirm(`确定删除「${item.nickname}」及其本地记录吗？`, '删除好友', { type: 'warning' }); await api.deleteUser(item.id); await load(); ElMessage.success('已删除') }
const priorityType = (value: Priority) => ({ high: 'danger', medium: 'warning', low: 'info' }[value] as 'danger' | 'warning' | 'info')
onMounted(load)
</script>

<template>
  <div><section class="toolbar"><div><h2>好友关系档案</h2><p>关系标签和优先级会参与 Agent 的提醒判断。</p></div><el-button type="primary" :icon="Plus" @click="open()">添加好友</el-button></section><div class="panel"><el-table :data="users" v-loading="!users"><el-table-column prop="nickname" label="昵称" min-width="130"><template #default="{ row }"><div class="name-cell"><span class="avatar small">{{ row.nickname.slice(0, 1) }}</span><b>{{ row.nickname }}</b></div></template></el-table-column><el-table-column prop="relationship" label="关系类型" min-width="120"/><el-table-column label="标签" min-width="220"><template #default="{ row }"><el-tag v-for="tag in row.tags" :key="tag" size="small" class="tag">{{ tag }}</el-tag><span v-if="!row.tags.length" class="muted">未添加</span></template></el-table-column><el-table-column label="优先级" min-width="120"><template #default="{ row }"><el-tag :type="priorityType(row.priority)">{{ row.priority === 'high' ? '高' : row.priority === 'medium' ? '中' : '低' }}</el-tag></template></el-table-column><el-table-column label="操作" width="150"><template #default="{ row }"><el-button text type="primary" :icon="Edit" @click="open(row)">编辑</el-button><el-button text type="danger" :icon="Delete" @click="remove(row)">删除</el-button></template></el-table-column></el-table></div>
    <el-dialog v-model="dialog" :title="editing ? '编辑好友' : '添加好友'" width="460px"><el-form label-position="top"><el-form-item label="昵称" required><el-input v-model="form.nickname" :disabled="!!editing" placeholder="例如：张三"/></el-form-item><el-form-item label="关系类型"><el-input v-model="form.relationship" placeholder="例如：大学同学"/></el-form-item><el-form-item label="优先级"><el-radio-group v-model="form.priority"><el-radio-button value="high">高</el-radio-button><el-radio-button value="medium">中</el-radio-button><el-radio-button value="low">低</el-radio-button></el-radio-group></el-form-item><el-form-item label="标签"><el-input v-model="form.tagsText" placeholder="游戏, 工作, 同学（用逗号分隔）"/></el-form-item></el-form><template #footer><el-button @click="dialog = false">取消</el-button><el-button type="primary" :disabled="!form.nickname" @click="save">保存</el-button></template></el-dialog>
  </div>
</template>
