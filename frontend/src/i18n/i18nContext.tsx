import React, { createContext, useContext, useState, useEffect, type ReactNode } from "react";
import { SUPPORTED_LANGUAGES, DEFAULT_LANGUAGE, type LanguageDefinition } from "./languages";
import { en } from "./locales/en";
import { hi } from "./locales/hi";
import { kn } from "./locales/kn";
import { ta } from "./locales/ta";
import { te } from "./locales/te";
import { ml } from "./locales/ml";
import { bn } from "./locales/bn";
import { apiClient } from "../services/api";

const translations: Record<string, any> = {
  en,
  hi,
  kn,
  ta,
  te,
  ml,
  bn,
};

interface I18nContextType {
  language: string;
  setLanguage: (lang: string) => void;
  currentLanguageDef: LanguageDefinition;
  supportedLanguages: LanguageDefinition[];
  t: (path: string, params?: Record<string, string | number>) => string;
}

const I18nContext = createContext<I18nContextType | undefined>(undefined);

const STORAGE_KEY = "relay_language";

export const I18nProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [language, setLanguageState] = useState<string>(() => {
    return localStorage.getItem(STORAGE_KEY) || DEFAULT_LANGUAGE;
  });

  const setLanguage = (lang: string) => {
    if (translations[lang]) {
      setLanguageState(lang);
      localStorage.setItem(STORAGE_KEY, lang);
      apiClient.setLanguage(lang);
      document.documentElement.lang = lang;
    }
  };

  useEffect(() => {
    apiClient.setLanguage(language);
    document.documentElement.lang = language;
  }, [language]);

  const currentLanguageDef =
    SUPPORTED_LANGUAGES.find((l) => l.code === language) ||
    SUPPORTED_LANGUAGES[0];

  const t = (path: string, params?: Record<string, string | number>): string => {
    const keys = path.split(".");
    let current: any = translations[language];

    // Traverse current locale
    for (const key of keys) {
      if (current && typeof current === "object" && key in current) {
        current = current[key];
      } else {
        current = undefined;
        break;
      }
    }

    // Fallback to English if key missing in current language
    if (current === undefined || typeof current !== "string") {
      let fallback: any = translations[DEFAULT_LANGUAGE];
      for (const key of keys) {
        if (fallback && typeof fallback === "object" && key in fallback) {
          fallback = fallback[key];
        } else {
          fallback = undefined;
          break;
        }
      }
      current = fallback !== undefined ? fallback : path;
    }

    if (typeof current === "string" && params) {
      return Object.entries(params).reduce((str, [k, v]) => {
        return str.replace(new RegExp(`\\{${k}\\}`, "g"), String(v));
      }, current);
    }

    return typeof current === "string" ? current : path;
  };

  return (
    <I18nContext.Provider
      value={{
        language,
        setLanguage,
        currentLanguageDef,
        supportedLanguages: SUPPORTED_LANGUAGES,
        t,
      }}
    >
      {children}
    </I18nContext.Provider>
  );
};

export const useTranslation = (): I18nContextType => {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error("useTranslation must be used within an I18nProvider");
  }
  return context;
};
