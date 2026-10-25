export type BusinessProfile = { businessType?: string; location?: string; offerings?: string; customers?: string; currentApproach?: string; constraints?: string };
export type OwnerContext = { goal: string; profile: BusinessProfile };
export type ResearchInput = { businessWebsite: string; competitors: string[]; businessName?: string; goal?: string; profile?: BusinessProfile };
export type Source = { id: string; title: string; url: string; retrievedAt: string; excerpt: string };
export type Recommendation = { id: string; title: string; rationale: string; action: string; effort: string; metric: string; ownerChecks: string[]; sourceIds: string[]; draft: { channel: string; title: string; body: string } };
export type Business = { name: string; url: string; role: 'owner' | 'competitor'; status: 'reviewed' | 'unavailable'; summary: string; sourceIds: string[] };
export type Report = { id: string; mode: 'live' | 'example'; businessName: string; businessWebsite: string; generatedAt: string; summary: string; limitations: string[]; businesses: Business[]; sources: Source[]; recommendations: Recommendation[]; ownerContext?: OwnerContext; usage?: { inputTokens: number; outputTokens: number } };
