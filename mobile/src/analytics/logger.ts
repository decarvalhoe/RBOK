/* eslint-disable no-console */
type AnalyticsEvent = {
  name: string;
  properties?: Record<string, unknown>;
};

type AnalyticsError = {
  message: string;
  context?: Record<string, unknown>;
};

export const logEvent = ({ name, properties }: AnalyticsEvent) => {
  console.log(`[analytics] event=${name}`, properties ?? {});
};

export const logError = ({ message, context }: AnalyticsError) => {
  console.error(`[analytics] error=${message}`, context ?? {});
};
