export type ProcedureStep = {
  key: string;
  title: string;
  prompt: string;
  slots: Array<Record<string, unknown>>;
};

export type Procedure = {
  id: string;
  name: string;
  description: string;
  steps: ProcedureStep[];
};

export type ProcedureRun = {
  id: string;
  procedure_id: string;
  user_id: string;
  state: string;
  created_at: string;
  closed_at?: string | null;
};
