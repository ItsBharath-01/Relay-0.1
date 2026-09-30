import { create } from "zustand";
import type { VoiceState, VoiceCommandResponse } from "../types";
import { apiClient } from "../services/api";

interface VoiceStoreState {
  voiceState: VoiceState;
  transcript: string;
  interimTranscript: string;
  lastReply: string;
  lastResponse: VoiceCommandResponse | null;
  actionTaken: string | null;
  isSupported: boolean;
  isOpen: boolean;

  // When voiceState === "confirmation_required", this holds the pending intent
  pendingConfirmation: {
    transcript: string;
    lang: string;
    executionId?: string;
    question: string;
    intent: string;
    confidence: number;
  } | null;

  setIsOpen: (open: boolean) => void;
  startListening: (speechCode?: string, executionId?: string) => void;
  stopListening: () => void;
  speak: (text: string, speechCode?: string) => void;
  stopSpeaking: () => void;
  processCommand: (
    transcript: string,
    lang: string,
    executionId?: string
  ) => Promise<VoiceCommandResponse>;
  reset: () => void;
}

interface IWindow extends Window {
  webkitSpeechRecognition?: any;
  SpeechRecognition?: any;
}

export const useVoiceStore = create<VoiceStoreState>((set, get) => {
  const win =
    typeof window !== "undefined" ? (window as unknown as IWindow) : null;
  const SpeechRecognitionClass =
    win?.SpeechRecognition || win?.webkitSpeechRecognition;
  const isSupported = Boolean(
    SpeechRecognitionClass &&
      typeof window !== "undefined" &&
      window.speechSynthesis
  );

  let recognitionInstance: any = null;

  return {
    voiceState: "idle",
    transcript: "",
    interimTranscript: "",
    lastReply: "",
    lastResponse: null,
    actionTaken: null,
    isSupported,
    isOpen: false,
    pendingConfirmation: null,

    setIsOpen: (open) => set({ isOpen: open }),

    startListening: (speechCode = "en-IN", executionId) => {
      if (!isSupported || !SpeechRecognitionClass) {
        set({
          voiceState: "error",
          lastReply: "Speech recognition is not supported in this browser.",
        });
        return;
      }

      if (window.speechSynthesis) {
        window.speechSynthesis.cancel();
      }
      if (recognitionInstance) {
        try {
          recognitionInstance.stop();
        } catch (_e) {}
      }

      try {
        const recognition = new SpeechRecognitionClass();
        recognition.lang = speechCode;
        recognition.continuous = false;
        recognition.interimResults = true;
        recognitionInstance = recognition;

        recognition.onstart = () => {
          set({
            voiceState: "listening",
            transcript: "",
            interimTranscript: "",
            actionTaken: null,
            pendingConfirmation: null,
          });
        };

        recognition.onresult = (event: any) => {
          let interim = "";
          let final = "";

          for (let i = event.resultIndex; i < event.results.length; ++i) {
            if (event.results[i].isFinal) {
              final += event.results[i][0].transcript;
            } else {
              interim += event.results[i][0].transcript;
            }
          }

          if (final) {
            set({ transcript: final, interimTranscript: "", voiceState: "transcribing" });
            recognition.stop();
            get().processCommand(
              final,
              speechCode.split("-")[0] || "en",
              executionId
            );
          } else {
            set({ interimTranscript: interim });
          }
        };

        recognition.onerror = (e: any) => {
          console.warn("Speech recognition error:", e.error);
          set({ voiceState: "idle" });
        };

        recognition.onend = () => {
          const s = get().voiceState;
          if (s === "listening" || s === "transcribing") {
            set({ voiceState: "idle" });
          }
        };

        recognition.start();
      } catch (err: any) {
        set({
          voiceState: "error",
          lastReply: err.message || "Failed to start speech recognition",
        });
      }
    },

    stopListening: () => {
      if (recognitionInstance) {
        try {
          recognitionInstance.stop();
        } catch (_e) {}
      }
      set({ voiceState: "idle" });
    },

    speak: (text: string, speechCode = "en-IN") => {
      if (typeof window === "undefined" || !window.speechSynthesis) return;

      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = speechCode;
      utterance.rate = 1.0;
      utterance.pitch = 1.0;

      utterance.onstart = () => set({ voiceState: "speaking" });
      utterance.onend = () => set({ voiceState: "idle" });
      utterance.onerror = () => set({ voiceState: "idle" });

      window.speechSynthesis.speak(utterance);
    },

    stopSpeaking: () => {
      if (typeof window !== "undefined" && window.speechSynthesis) {
        window.speechSynthesis.cancel();
      }
      set({ voiceState: "idle" });
    },

    processCommand: async (
      transcript: string,
      lang: string,
      executionId?: string
    ): Promise<VoiceCommandResponse> => {
      set({ voiceState: "processing", transcript });
      try {
        const res = await apiClient.post<VoiceCommandResponse>(
          "/api/voice/process",
          {
            transcript,
            language: lang,
            execution_id: executionId,
          }
        );

        set({ lastResponse: res, actionTaken: res.action_taken ?? null });

        if (res.clarification_needed && res.clarification_question) {
          // Medium confidence OR low confidence — show confirmation UI
          set({
            voiceState: "confirmation_required",
            lastReply: res.reply_text,
            pendingConfirmation: {
              transcript,
              lang,
              executionId,
              question: res.clarification_question,
              intent: res.intent,
              confidence: res.confidence,
            },
          });
          get().speak(res.reply_text, `${lang}-IN`);
        } else {
          set({
            voiceState: "idle",
            lastReply: res.reply_text,
            pendingConfirmation: null,
          });
          get().speak(res.reply_text, `${lang}-IN`);
        }

        return res;
      } catch (err: any) {
        const errorReply =
          "Sorry, I could not process your voice command right now.";
        set({ voiceState: "idle", lastReply: errorReply, pendingConfirmation: null });
        get().speak(errorReply, `${lang}-IN`);
        throw err;
      }
    },

    reset: () => {
      get().stopSpeaking();
      get().stopListening();
      set({
        voiceState: "idle",
        transcript: "",
        interimTranscript: "",
        lastReply: "",
        lastResponse: null,
        actionTaken: null,
        pendingConfirmation: null,
      });
    },
  };
});
