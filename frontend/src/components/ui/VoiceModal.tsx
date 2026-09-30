/**
 * VoiceModal — P2-1 voice interface modal
 *
 * Renders the full voice interaction panel that slides in when the Mic button is pressed.
 * Uses useVoiceStore for all state; no direct Ollama calls.
 */

import React from "react";
import ReactDOM from "react-dom";
import {
  Mic,
  MicOff,
  X,
  Volume2,
  VolumeX,
  Loader2,
  CheckCircle2,
  HelpCircle,
  AlertTriangle,
} from "lucide-react";
import { useVoiceStore } from "../../stores/voiceStore";
import { useAuthStore } from "../../stores/authStore";
import type { VoiceState } from "../../types";

// ── Language code → BCP-47 speech code mapping ──────────────────────────────
const SPEECH_CODE_MAP: Record<string, string> = {
  en: "en-IN",
  hi: "hi-IN",
  kn: "kn-IN",
  ta: "ta-IN",
  te: "te-IN",
  ml: "ml-IN",
  bn: "bn-IN",
};

// ── State display config ─────────────────────────────────────────────────────
interface StateDisplay {
  label: string;
  color: string;
  pulse: boolean;
}

const STATE_DISPLAY: Record<VoiceState, StateDisplay> = {
  idle: { label: "Ready", color: "text-slate-500", pulse: false },
  listening: { label: "Listening…", color: "text-blue-600", pulse: true },
  transcribing: { label: "Transcribing…", color: "text-indigo-600", pulse: true },
  processing: { label: "Processing…", color: "text-violet-600", pulse: true },
  confirmation_required: {
    label: "Confirm?",
    color: "text-amber-600",
    pulse: false,
  },
  speaking: { label: "Speaking…", color: "text-emerald-600", pulse: true },
  error: { label: "Error", color: "text-rose-600", pulse: false },
};

// ── Confidence bar component ─────────────────────────────────────────────────
const ConfidenceBar: React.FC<{ value: number }> = ({ value }) => {
  const pct = Math.round(value * 100);
  const color =
    value >= 0.75
      ? "bg-emerald-500"
      : value >= 0.5
      ? "bg-amber-400"
      : "bg-rose-400";

  return (
    <div className="flex items-center gap-2 text-xs text-slate-500">
      <span>Confidence</span>
      <div className="flex-1 h-1.5 rounded-full bg-slate-200 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="tabular-nums">{pct}%</span>
    </div>
  );
};

// ── Mic visual ───────────────────────────────────────────────────────────────
const MicVisual: React.FC<{ state: VoiceState; onPress: () => void; onStop: () => void }> = ({
  state,
  onPress,
  onStop,
}) => {
  const isActive =
    state === "listening" ||
    state === "transcribing" ||
    state === "processing";

  const ringClasses =
    state === "listening"
      ? "ring-4 ring-blue-400/50 animate-pulse"
      : state === "processing" || state === "transcribing"
      ? "ring-4 ring-violet-400/50"
      : "";

  return (
    <div className="flex flex-col items-center gap-3">
      <button
        onClick={isActive ? onStop : onPress}
        disabled={state === "processing" || state === "transcribing" || state === "speaking"}
        className={`
          relative w-20 h-20 rounded-full flex items-center justify-center
          transition-all duration-200 focus:outline-none focus-visible:ring-2
          focus-visible:ring-offset-2 focus-visible:ring-blue-500
          ${isActive ? "bg-blue-600 text-white shadow-lg" : "bg-slate-100 text-slate-600 hover:bg-blue-50 hover:text-blue-600"}
          ${state === "speaking" ? "bg-emerald-100 text-emerald-600 cursor-default" : ""}
          ${state === "processing" || state === "transcribing" ? "cursor-default opacity-80" : ""}
          ${ringClasses}
        `}
        aria-label={isActive ? "Stop listening" : "Start listening"}
      >
        {state === "processing" || state === "transcribing" ? (
          <Loader2 className="w-8 h-8 animate-spin" />
        ) : state === "speaking" ? (
          <Volume2 className="w-8 h-8" />
        ) : isActive ? (
          <MicOff className="w-8 h-8" />
        ) : (
          <Mic className="w-8 h-8" />
        )}
      </button>
      <StateLabel state={state} />
    </div>
  );
};

const StateLabel: React.FC<{ state: VoiceState }> = ({ state }) => {
  const { label, color, pulse } = STATE_DISPLAY[state];
  return (
    <span className={`text-sm font-medium ${color} ${pulse ? "animate-pulse" : ""}`}>
      {label}
    </span>
  );
};

// ── Main VoiceModal ──────────────────────────────────────────────────────────
export const VoiceModal: React.FC = () => {
  const {
    isOpen,
    isSupported,
    voiceState,
    transcript,
    interimTranscript,
    lastReply,
    lastResponse,
    actionTaken,
    pendingConfirmation,
    setIsOpen,
    startListening,
    stopListening,
    stopSpeaking,
    processCommand,
    reset,
  } = useVoiceStore();

  const { user } = useAuthStore();

  // Derive speech code from user language preference
  const lang = user?.preferences?.language ?? "en";
  const speechCode = SPEECH_CODE_MAP[lang] ?? "en-IN";

  // Close handler
  const handleClose = () => {
    reset();
    setIsOpen(false);
  };

  // Escape key
  React.useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") handleClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [isOpen]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!isOpen) return null;

  // ── Not supported ──
  if (!isSupported) {
    return ReactDOM.createPortal(
      <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4">
        <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={handleClose} />
        <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-sm border border-slate-200 p-6">
          <div className="flex items-center gap-3 mb-4">
            <AlertTriangle className="w-6 h-6 text-amber-500 shrink-0" />
            <h2 className="text-base font-bold text-slate-900">Voice Unavailable</h2>
            <button onClick={handleClose} className="ml-auto p-1.5 text-slate-400 hover:text-slate-600">
              <X className="w-4 h-4" />
            </button>
          </div>
          <p className="text-sm text-slate-600">
            Your browser does not support the Web Speech API. Please use Chrome or Edge to
            use voice commands.
          </p>
        </div>
      </div>,
      document.body
    );
  }

  return ReactDOM.createPortal(
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-sm"
        onClick={handleClose}
      />

      {/* Panel */}
      <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-sm border border-slate-200 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
          <div className="flex items-center gap-2">
            <Mic className="w-4 h-4 text-blue-600" />
            <h2 className="text-base font-bold text-slate-900">Voice Command</h2>
          </div>
          <div className="flex items-center gap-2">
            {voiceState === "speaking" && (
              <button
                onClick={stopSpeaking}
                className="p-1.5 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-100"
                aria-label="Stop speaking"
              >
                <VolumeX className="w-4 h-4" />
              </button>
            )}
            <button
              onClick={handleClose}
              className="p-1.5 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-100"
              aria-label="Close"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="px-5 py-6 flex flex-col items-center gap-5">
          {/* Mic button */}
          <MicVisual
            state={voiceState}
            onPress={() => startListening(speechCode)}
            onStop={stopListening}
          />

          {/* Transcript live display */}
          {(transcript || interimTranscript) && (
            <div className="w-full rounded-xl bg-slate-50 border border-slate-200 px-4 py-3">
              <p className="text-xs text-slate-400 mb-1">You said</p>
              <p className="text-sm text-slate-800 leading-relaxed">
                {transcript || (
                  <span className="italic text-slate-400">{interimTranscript}</span>
                )}
              </p>
            </div>
          )}

          {/* Confidence bar */}
          {lastResponse && lastResponse.confidence > 0 && (
            <div className="w-full">
              <ConfidenceBar value={lastResponse.confidence} />
            </div>
          )}

          {/* Confirmation required */}
          {voiceState === "confirmation_required" && pendingConfirmation && (
            <div className="w-full rounded-xl bg-amber-50 border border-amber-200 px-4 py-3">
              <div className="flex items-start gap-2">
                <HelpCircle className="w-4 h-4 text-amber-500 mt-0.5 shrink-0" />
                <div className="flex-1">
                  <p className="text-xs font-medium text-amber-700 mb-1">Confirm</p>
                  <p className="text-sm text-amber-800">{pendingConfirmation.question}</p>
                </div>
              </div>
              <div className="flex gap-2 mt-3">
                <button
                  onClick={async () => {
                    // Re-send same transcript but let backend treat it as explicit confirmation
                    // by sending the transcript again; the LLM should return high confidence
                    // for a repeat of the same command with context.
                    await processCommand(
                      pendingConfirmation.transcript,
                      pendingConfirmation.lang,
                      pendingConfirmation.executionId
                    );
                  }}
                  className="flex-1 py-2 text-xs font-semibold bg-amber-500 text-white rounded-lg hover:bg-amber-600 transition-colors"
                >
                  Yes, confirm
                </button>
                <button
                  onClick={reset}
                  className="flex-1 py-2 text-xs font-semibold bg-white text-slate-600 border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* Last reply */}
          {lastReply && voiceState !== "confirmation_required" && (
            <div className="w-full rounded-xl bg-blue-50 border border-blue-100 px-4 py-3">
              <p className="text-xs text-blue-400 mb-1">Relay said</p>
              <p className="text-sm text-blue-800 leading-relaxed">{lastReply}</p>
            </div>
          )}

          {/* Action taken */}
          {actionTaken && (
            <div className="flex items-center gap-2 text-xs text-emerald-600 font-medium">
              <CheckCircle2 className="w-3.5 h-3.5" />
              Action taken: {actionTaken}
            </div>
          )}

          {/* Intent badge */}
          {lastResponse && lastResponse.intent !== "unknown" && voiceState === "idle" && (
            <p className="text-xs text-slate-400">
              Detected:{" "}
              <span className="font-medium text-slate-600">
                {lastResponse.intent.replace(/_/g, " ")}
              </span>
              {lastResponse.llm_used ? " · via LLM" : " · LLM unavailable"}
            </p>
          )}

          {/* LLM unavailable notice */}
          {lastResponse && !lastResponse.llm_used && (
            <p className="text-xs text-amber-500">
              AI assistant is currently unavailable. Voice commands are limited.
            </p>
          )}
        </div>

        {/* Footer hint */}
        <div className="px-5 pb-4 text-center">
          <p className="text-xs text-slate-400">
            {voiceState === "idle"
              ? "Press the mic and speak your command"
              : voiceState === "listening"
              ? "Speak now…"
              : voiceState === "processing" || voiceState === "transcribing"
              ? "Thinking…"
              : voiceState === "speaking"
              ? "Tap the speaker icon to stop"
              : voiceState === "confirmation_required"
              ? "Confirm or cancel above"
              : null}
          </p>
        </div>
      </div>
    </div>,
    document.body
  );
};
