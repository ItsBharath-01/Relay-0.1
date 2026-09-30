import { create } from "zustand";
import type { GoalUnderstanding, Plan } from "../types";
import { apiClient } from "../services/api";

interface GoalUnderstandResponse {
  goal_id?: string;
  original_goal: string;
  language: string;
  understanding: GoalUnderstanding;
  provider_meta?: Record<string, any>;
}

interface GoalState {
  currentGoalText: string;
  currentLanguage: string;
  goalId: string | null;
  understanding: GoalUnderstanding | null;
  clarificationAnswers: Record<string, string>;
  isAnalyzing: boolean;
  isGeneratingPlan: boolean;
  currentPlan: Plan | null;
  error: string | null;

  setGoalText: (text: string) => void;
  setLanguage: (lang: string) => void;
  setClarificationAnswer: (questionId: string, answer: string) => void;
  analyzeGoal: (goalText?: string, language?: string) => Promise<GoalUnderstanding>;
  submitClarifications: () => Promise<GoalUnderstanding>;
  generatePlan: () => Promise<Plan>;
  fetchPlan: (planId: string) => Promise<Plan>;
  reset: () => void;
}

export const useGoalStore = create<GoalState>((set, get) => ({
  currentGoalText: "",
  currentLanguage: "en",
  goalId: null,
  understanding: null,
  clarificationAnswers: {},
  isAnalyzing: false,
  isGeneratingPlan: false,
  currentPlan: null,
  error: null,

  setGoalText: (text) => set({ currentGoalText: text }),
  setLanguage: (lang) => set({ currentLanguage: lang }),
  setClarificationAnswer: (questionId, answer) =>
    set((state) => ({
      clarificationAnswers: { ...state.clarificationAnswers, [questionId]: answer },
    })),

  analyzeGoal: async (goalText?: string, language?: string) => {
    const text = goalText ?? get().currentGoalText;
    const lang = language ?? get().currentLanguage;
    if (!text.trim()) {
      throw new Error("Goal text cannot be empty");
    }

    set({ isAnalyzing: true, error: null, currentGoalText: text, currentLanguage: lang });

    try {
      const res = await apiClient.post<GoalUnderstandResponse>("/api/goals/understand", {
        goal: text,
        language: lang,
      });

      set({
        goalId: res.goal_id || null,
        understanding: res.understanding,
        isAnalyzing: false,
        error: null,
      });
      return res.understanding;
    } catch (err: any) {
      set({ isAnalyzing: false, error: err.message || "Failed to analyze goal" });
      throw err;
    }
  },

  submitClarifications: async () => {
    const { currentGoalText, currentLanguage, clarificationAnswers, goalId } = get();
    set({ isAnalyzing: true, error: null });

    try {
      const res = await apiClient.post<GoalUnderstandResponse>("/api/goals/understand", {
        goal_id: goalId,
        goal: currentGoalText,
        language: currentLanguage,
        clarification_answers: clarificationAnswers,
      });

      set({
        goalId: res.goal_id || null,
        understanding: res.understanding,
        isAnalyzing: false,
        error: null,
      });
      return res.understanding;
    } catch (err: any) {
      set({ isAnalyzing: false, error: err.message || "Failed to process clarifications" });
      throw err;
    }
  },

  generatePlan: async () => {
    const { goalId } = get();
    if (!goalId) {
      throw new Error("Goal must be analyzed first before generating plan");
    }

    set({ isGeneratingPlan: true, error: null });
    try {
      const plan = await apiClient.post<Plan>("/api/plans/generate", {
        goal_id: goalId,
      });
      set({ currentPlan: plan, isGeneratingPlan: false, error: null });
      return plan;
    } catch (err: any) {
      set({ isGeneratingPlan: false, error: err.message || "Failed to generate plan" });
      throw err;
    }
  },

  fetchPlan: async (planId: string) => {
    set({ isGeneratingPlan: true, error: null });
    try {
      const plan = await apiClient.get<Plan>(`/api/plans/${planId}`);
      set({ currentPlan: plan, isGeneratingPlan: false, error: null });
      return plan;
    } catch (err: any) {
      set({ isGeneratingPlan: false, error: err.message || "Failed to fetch plan" });
      throw err;
    }
  },

  reset: () =>
    set({
      currentGoalText: "",
      goalId: null,
      understanding: null,
      clarificationAnswers: {},
      isAnalyzing: false,
      isGeneratingPlan: false,
      currentPlan: null,
      error: null,
    }),
}));
