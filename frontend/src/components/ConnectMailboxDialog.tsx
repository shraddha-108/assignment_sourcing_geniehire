import React from "react";
import type { MailboxProvider } from "../features/outreach/outreachSequence";

type ConnectMailboxDialogProps = {
  isOpen: boolean;
  onClose: () => void;
  onConnect: (provider: MailboxProvider, email?: string) => void;
  onDoLater: () => void;
};

export const ConnectMailboxDialog: React.FC<ConnectMailboxDialogProps> = ({
  isOpen,
  onClose,
  onConnect,
  onDoLater,
}) => {
  if (!isOpen) return null;

  return (
    <div className="mailbox-modal-overlay" role="dialog" aria-modal="true" aria-labelledby="mailbox-modal-title">
      <div className="mailbox-modal-backdrop" onClick={onClose} />
      <div className="mailbox-modal-card">
        <button
          type="button"
          className="mailbox-close-button"
          onClick={onClose}
          aria-label="Close"
        >
          Close
        </button>

        <div className="mailbox-modal-content">
          <h2 id="mailbox-modal-title" className="mailbox-title">
            Connect your mailbox
          </h2>

          <div className="mailbox-options">
            <button
              type="button"
              className="mailbox-option-button"
              onClick={() => onConnect("gmail", "recruiter@gmail.com")}
            >
              <span className="mailbox-icon gmail-icon">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                  <path
                    d="M22 6c0-1.1-.9-2-2-2H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6zm-2 0l-8 5-8-5h16zm0 12H4V8l8 5 8-5v10z"
                    fill="#EA4335"
                  />
                  <path d="M4 6l8 5 8-5H4z" fill="#4285F4" />
                </svg>
              </span>
              <span>Connect Gmail</span>
            </button>

            <button
              type="button"
              className="mailbox-option-button"
              onClick={() => onConnect("outlook", "recruiter@outlook.com")}
            >
              <span className="mailbox-icon outlook-icon">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                  <rect x="2" y="2" width="9" height="9" fill="#F25022" />
                  <rect x="13" y="2" width="9" height="9" fill="#7FBA00" />
                  <rect x="2" y="13" width="9" height="9" fill="#00A4EF" />
                  <rect x="13" y="13" width="9" height="9" fill="#FFB900" />
                </svg>
              </span>
              <span>Connect Outlook</span>
            </button>

            <button
              type="button"
              className="mailbox-option-button"
              onClick={() => onConnect("imap", "recruiter@company.com")}
            >
              <span className="mailbox-icon imap-icon">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
                  <polyline points="22,6 12,13 2,6" />
                </svg>
              </span>
              <span>Connect IMAP</span>
            </button>

            <div className="mailbox-divider">
              <span>Or</span>
            </div>

            <button
              type="button"
              className="mailbox-option-button mailbox-later-button"
              onClick={onDoLater}
            >
              <span className="mailbox-icon later-icon">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10" />
                  <polyline points="12 6 12 12 16 14" />
                </svg>
              </span>
              <span>Do this later</span>
            </button>
          </div>

          <div className="mailbox-footer">
            <p>Having trouble connecting?</p>
            <p>Manage mailbox settings in the <strong>Integrations page</strong></p>
          </div>
        </div>
      </div>
    </div>
  );
};
