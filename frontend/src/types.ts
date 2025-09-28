export interface Job {
  id: number;
  title: string;
  company: string;
  location?: string | null;
  url: string;
  posted_at?: string | null;
  created_at?: string | null;
  source: string;
  req_id: string;
}

export interface ToastMessage {
  id: string;
  title: string;
  description?: string;
  url?: string;
}
