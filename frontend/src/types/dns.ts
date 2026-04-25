export type DnsAlertType = "DGA_DOMAIN" | "DNS_TUNNELING";

export interface DnsEntry {
  ts: string;
  domain: string;
  qtype: string;
  src_ip: string;
  alert_type: DnsAlertType | null;
  entropy: number | null;
}

export interface DnsAlert {
  ts: string;
  type: DnsAlertType;
  domain: string;
  src_ip: string;
  entropy: number | null;
  description: string;
}

export interface DeviceDnsSummary {
  total_queries: number;
  alert_count: number;
  top_domains: { domain: string; count: number }[];
  available: boolean;
}
