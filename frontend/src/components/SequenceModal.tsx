import React, { useState } from "react";
import type { Candidate } from "../types/candidate";
import {
  DEFAULT_SEQUENCES,
  interpolateTemplate,
  type Sequence,
} from "../features/outreach/outreachSequence";

type SequenceModalProps = {
  isOpen: boolean;
  onClose: () => void;
  candidates: Candidate[];
  onEnroll: (candidateIds: number[], sequenceId: string) => void;
  searchQuery?: string;
};

export const SequenceModal: React.FC<SequenceModalProps> = ({
  isOpen,
  onClose,
  candidates,
  onEnroll,
  searchQuery = "our open role",
}) => {
  const [selectedSequenceId, setSelectedSequenceId] = useState<string>(
    DEFAULT_SEQUENCES[0]?.id || ""
  );

  if (!isOpen || candidates.length === 0) return null;

  const currentSequence: Sequence | undefined =
    DEFAULT_SEQUENCES.find((s) => s.id === selectedSequenceId) ||
    DEFAULT_SEQUENCES[0];

  const primaryCandidate = candidates[0];
  const firstName = primaryCandidate.name.split(/\s+/)[0] ?? primaryCandidate.name;
  const company =
    primaryCandidate.experience_timeline?.[0]?.company ||
    "their current company";
  const role =
    primaryCandidate.experience_timeline?.[0]?.role ||
    primaryCandidate.headline ||
    "Software Engineer";
  const topSkill =
    primaryCandidate.matched_skills?.[0]?.skill ||
    primaryCandidate.profile_skills?.[0] ||
    "engineering";

  const handleEnroll = () => {
    if (!currentSequence) return;
    const ids = candidates.map((c) => c.id);
    onEnroll(ids, currentSequence.id);
    onClose();
  };

  return (
    <div className="sequence-modal-overlay" role="dialog" aria-modal="true" aria-labelledby="sequence-modal-title">
      <div className="sequence-modal-backdrop" onClick={onClose} />
      <div className="sequence-modal-card">
        <div className="sequence-modal-header">
          <div>
            <h2 id="sequence-modal-title" className="sequence-modal-title">
              Add to Sequence
            </h2>
            <p className="sequence-modal-subtitle">
              {candidates.length === 1
                ? `Enroll ${primaryCandidate.name} into an automated follow-up campaign`
                : `Enroll ${candidates.length} selected candidates into an automated follow-up campaign`}
            </p>
          </div>
          <button
            type="button"
            className="sequence-close-btn"
            onClick={onClose}
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <div className="sequence-modal-body">
          <div className="sequence-select-group">
            <label htmlFor="sequence-select">Select Sequence</label>
            <select
              id="sequence-select"
              className="sequence-dropdown"
              value={selectedSequenceId}
              onChange={(e) => setSelectedSequenceId(e.target.value)}
            >
              {DEFAULT_SEQUENCES.map((seq) => (
                <option key={seq.id} value={seq.id}>
                  {seq.name} ({seq.steps.length} steps)
                </option>
              ))}
            </select>
          </div>

          <div className="sequence-steps-container">
            <h4 className="sequence-preview-heading">Sequence Timeline Preview</h4>
            {currentSequence?.steps.map((step, index) => {
              const previewSubject = interpolateTemplate(step.subject, {
                firstName,
                company,
                role,
                topSkill,
                searchQuery,
              });
              const previewBody = interpolateTemplate(step.body, {
                firstName,
                company,
                role,
                topSkill,
                searchQuery,
              });

              return (
                <div key={step.id} className="sequence-step-card">
                  <div className="sequence-step-marker">
                    <span className="step-badge">{index + 1}</span>
                    <span className="step-delay">
                      {step.delayDays === 0
                        ? "Day 1 (Immediate)"
                        : `+${step.delayDays} days after Step ${index}`}
                    </span>
                  </div>
                  <div className="sequence-step-content">
                    <div className="step-subject">
                      <strong>Subject:</strong> {previewSubject}
                    </div>
                    <div className="step-body-preview">{previewBody}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="sequence-modal-footer">
          <button
            type="button"
            className="candidate-action-button"
            onClick={onClose}
          >
            Cancel
          </button>
          <button
            type="button"
            className="candidate-action-button candidate-action-primary sequence-enroll-button"
            onClick={handleEnroll}
          >
            {candidates.length === 1
              ? `Enroll ${firstName}`
              : `Enroll ${candidates.length} Candidates`}
          </button>
        </div>
      </div>
    </div>
  );
};
