export interface ChannelPluginStatus {
  plugin_id: string;
  id?: string;
  type: string;
  name: string;
  enabled: boolean;
  connected: boolean;
  has_token?: boolean;
  status?: string;
  last_connected?: number | null;
  active_users?: number;
  bot_username?: string | null;
  coming_soon?: boolean;
  error?: string | null;
}

export interface ChannelPairing {
  code: string;
  platform_user_id: string;
  platform_type: string;
  display_name?: string;
  chat_id?: string;
  requested_at: number;
  expires_at: number;
}

export interface ChannelUser {
  id: string;
  platform_user_id: string;
  platform_type: string;
  display_name?: string;
  chat_id?: string;
  authorized_at: number;
  last_active?: number;
}

export interface ChannelSettings {
  platform: string;
  assistant: { assistant_id?: string } | null;
  default_model: { id: string; use_model: string } | null;
}
