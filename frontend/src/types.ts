export interface User {
  id: string;
  full_name: string;
  email: string | null;
  phone: string | null;
  college: string | null;
  location_label: string | null;
  upi_id?: string | null;
  plan: string;
  verified_email: boolean;
  verified_phone: boolean;
  created_at?: string;
  completed_exchanges?: number;
  total_points?: number;
  points?: number;
  friend_count?: number;
  friends_count?: number;
}

export interface Listing {
  id: string;
  owner_id?: string;
  owner_name?: string;
  owner?: {
    id: string;
    full_name: string;
    college?: string | null;
    verified: boolean;
  };
  kind: 'need' | 'have';
  amount_min: number;
  amount_max: number;
  location: string;
  search_radius_km?: number;
  availability: string;
  note: string;
  status: string;
  distance_km?: number | null;
  created_at?: string;
  expires_at?: string;
  verified?: boolean;
  mine?: boolean;
  [key: string]: any;
}

export interface MatchRequest {
  id: string;
  seeker_id: string;
  provider_id: string;
  seeker_listing_id: string;
  provider_listing_id: string;
  seeker_name?: string;
  provider_name?: string;
  amount: number;
  note: string;
  status: 'pending' | 'accepted' | 'rejected' | 'expired' | 'cancelled';
  created_at: string;
  responded_at: string | null;
  expires_at: string;
  seeker_listing?: Listing;
  provider_listing?: Listing;
}

export interface Exchange {
  id: string;
  listing_id?: string;
  matched_listing_id?: string;
  requester_id: string;
  provider_id: string;
  amount: number;
  location: string;
  meetup_at: string;
  status: string;
  requester_arrived: boolean;
  provider_arrived: boolean;
  requester_cash_confirmed: boolean;
  provider_cash_confirmed: boolean;
  seeker_cash_received?: boolean;
  seeker_cash_received_at?: string | null;
  provider_upi_received?: boolean;
  provider_upi_received_at?: string | null;
  created_at?: string;
  completed_at?: string | null;
  cancelled_at?: string | null;
  dispute_reason?: string | null;
  payment_status?: string | null;
  requester_name?: string;
  provider_name?: string;
  other_user?: {
    id: string;
    full_name: string;
    college?: string | null;
  };
  events?: StatusEvent[];
  payments?: PaymentAttempt[];
  can_confirm_receipt?: boolean;
}

export interface Conversation {
  id: string;
  participant_a: string;
  participant_b: string;
  exchange_id: string | null;
  updated_at: string;
  other_user_id?: string;
  other_user_name?: string;
  other_user?: {
    id: string;
    full_name: string;
    college?: string | null;
  };
  last_message?: string;
  last_message_at?: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  sender_id: string;
  body: string;
  created_at: string;
}

export interface Notification {
  id: string;
  user_id: string;
  title: string;
  body: string;
  kind: string;
  read_at: string | null;
  created_at: string;
}

export interface PaymentAttempt {
  id: string;
  exchange_id: string;
  payer_id: string;
  payee_upi: string;
  amount: number;
  reference: string;
  status: string;
  provider: string;
  provider_utr: string | null;
  receiver_confirmed_by: string | null;
  receiver_confirmed_at: string | null;
  created_at: string;
  updated_at: string;
  upi_uri?: string;
  verification_note?: string;
}

export interface StatusEvent {
  id: string;
  exchange_id: string;
  actor_id: string | null;
  status: string;
  details: string;
  created_at: string;
}

export interface Subscription {
  current_plan: string;
  completed_this_month: number;
  reserved: number;
  monthly_limit: number | null;
  remaining: number | null;
  billing_configured: boolean;
  catalog: PlanInfo[];
}

export interface PlanInfo {
  name: string;
  price: number;
  limit: number | null;
  label: string;
}

export interface PointEntry {
  id: string;
  amount: number;
  reason: string;
  created_at: string;
}

export type Screen =
  | 'welcome'
  | 'signup'
  | 'login'
  | 'verify'
  | 'home'
  | 'matches'
  | 'need'
  | 'have'
  | 'chats'
  | 'scan'
  | 'transactions'
  | 'profile'
  | 'meetup'
  | 'student'
  | 'notifications'
  | 'subscriptions'
  | 'points'
  | 'location'
  | 'help'
  | 'payment'
  | 'match-requests';

export type OtpChannel = 'mobile' | 'email';

export type OtpRequestResult = {
  accepted: true;
  challenge_id: string;
  expires_in_seconds: number;
  resend_in_seconds: number;
  channel: OtpChannel;
  contact: string;
  intent: 'signup' | 'login';
  full_name?: string;
  college?: string | null;
  development_code?: string;
};

export type Coordinates = {
  latitude: number;
  longitude: number;
};

export type GeoStatus =
  | 'checking'
  | 'prompt'
  | 'loading'
  | 'ready'
  | 'denied'
  | 'unavailable'
  | 'error'
  | 'insecure';

export type Payment = {
  id: string;
  reference: string;
  amount: number;
  status: string;
  upi_uri: string;
  verification_note: string;
};
