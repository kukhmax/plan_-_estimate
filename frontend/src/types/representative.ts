export type RepresentativeSide = 'CUSTOMER' | 'CUSTOMER_REPRESENTATIVE' | 'SUPERVISION' | 'CONTRACTOR';

export const REPRESENTATIVE_SIDES: RepresentativeSide[] = ['CUSTOMER', 'CUSTOMER_REPRESENTATIVE', 'SUPERVISION', 'CONTRACTOR'];

/** A person of an object (Stage 16B.2): who acts for a side and whether they may accept the work and sign the protocols. */
export interface ProjectRepresentative {
  id: string;
  project_id: string;
  side: RepresentativeSide;
  name: string;
  role_title: string | null;
  phone: string | null;
  email: string | null;
  may_accept_and_sign: boolean;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProjectRepresentativeListResponse {
  items: ProjectRepresentative[];
  total: number;
}

export interface ProjectRepresentativeCreatePayload {
  side: RepresentativeSide;
  name: string;
  role_title?: string;
  phone?: string;
  email?: string;
  may_accept_and_sign: boolean;
}

/** Only what changes is sent; null clears an optional field. */
export interface ProjectRepresentativeUpdatePayload {
  side?: RepresentativeSide;
  name?: string;
  role_title?: string | null;
  phone?: string | null;
  email?: string | null;
  may_accept_and_sign?: boolean;
}
