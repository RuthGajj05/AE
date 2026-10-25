import type { BusinessProfile } from './types';

export const profileFields = [
  { key: 'businessType', label: 'Business type', maxLength: 100, placeholder: 'Bakery, dog groomer, bike shop…' },
  { key: 'location', label: 'Location or service area', maxLength: 160, placeholder: 'Neighborhood, city, or area you serve' },
  { key: 'offerings', label: 'What do you sell or offer?', maxLength: 600, placeholder: 'Your main products or services, and what makes them different' },
  { key: 'customers', label: 'Who are you trying to reach?', maxLength: 400, placeholder: 'For example, nearby office workers who need a quick weekday lunch' },
  { key: 'currentApproach', label: 'What are you already doing?', maxLength: 600, placeholder: 'Existing offers, marketing, tools, or things you have already tried' },
  { key: 'constraints', label: 'What should we work around?', maxLength: 600, placeholder: 'Available time, budget, capacity, or things you do not want to change' },
] as const satisfies ReadonlyArray<{ key: keyof BusinessProfile; label: string; maxLength: number; placeholder: string }>;

export function hasProfileAnswers(profile: BusinessProfile | undefined): boolean {
  return Boolean(profile && profileFields.some(field => profile[field.key]?.trim()));
}
