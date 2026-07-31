export type Priority = 'low' | 'medium' | 'high'
export type SuggestionStatus = 'pending' | 'copied' | 'dismissed' | 'used'

export interface User { id: number; nickname: string; relationship: string; priority: Priority; tags: string[]; created_at: string }
export interface Interaction { id: number; user_id: number; time: string; content: string; status: string; source: string }
export interface Suggestion { id: number; user_id: number; nickname?: string; content: string; tone: string; reason: string; risk_level: string; status: SuggestionStatus; created_at: string }
export interface Dashboard { today_needing_attention: number; high_priority_users: User[]; pending_suggestions: number; recent_interactions: Interaction[] }
export interface Scan { id: number; status: string; source: string; screenshot_path: string | null; result_count: number; error: string | null; created_at: string; completed_at: string | null }
export interface Settings { scan_time: string; scan_frequency: string; ocr_region: number[] | null; keep_screenshots: boolean; llm_configured: boolean }

