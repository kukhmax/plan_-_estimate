/** A note of the owner on an object (Stage 18); mirrors backend `ProjectNoteRead`. */
export interface ProjectNote {
  id: string;
  project_id: string;
  body: string;
  created_at: string;
  updated_at: string;
  /** Made on the phone and not yet accepted by the server (Stage 19E): the screens mark it. */
  _pending?: boolean;
}

export interface ProjectNoteList {
  items: ProjectNote[];
  total: number;
}

/** Same limit as the backend (`MAX_NOTE_LENGTH`). */
export const MAX_NOTE_LENGTH = 4000;
