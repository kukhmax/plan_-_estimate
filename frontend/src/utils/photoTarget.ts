import { PhotoAttachmentRead, PhotoContext, PhotoTarget } from '../types/photo';

/** The leaf id of a target (undefined for PROJECT). For INSPECTION it is the inspection, for FINDING the finding row, for WORK the surface. */
export function targetIdOf(
  target: Pick<PhotoTarget, 'context' | 'roomId' | 'surfaceId' | 'openingId' | 'inspectionId' | 'findingId' | 'paymentId'>,
): string | undefined {
  if (target.context === 'ROOM') return target.roomId;
  if (target.context === 'SURFACE' || target.context === 'WORK') return target.surfaceId; // WORK: the surface; its occurrence is the scope
  if (target.context === 'OPENING') return target.openingId;
  if (target.context === 'INSPECTION') return target.inspectionId;
  if (target.context === 'FINDING') return target.findingId;
  if (target.context === 'PAYMENT') return target.paymentId; // IA-3: the settlement record
  return undefined;
}

/** Context and leaf id of an existing attachment (what the counts endpoint groups by); the question of a question-level photo, the occurrence of a WORK photo. */
export function attachmentTarget(attachment: PhotoAttachmentRead): {
  context: PhotoContext;
  targetId: string | undefined;
  questionId: string | undefined;
  occurrenceKey: string | undefined;
} {
  return {
    context: attachment.context as PhotoContext,
    targetId:
      attachment.room_id ??
      attachment.surface_id ??
      attachment.opening_id ??
      attachment.inspection_id ??
      attachment.finding_id ??
      attachment.payment_id ??
      undefined,
    questionId: attachment.question_id ?? undefined,
    occurrenceKey: attachment.occurrence_key ?? undefined,
  };
}
