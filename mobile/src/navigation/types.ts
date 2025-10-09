export type RootStackParamList = {
  Home: undefined;
  Procedures: undefined;
  ProcedureDetail: { procedureId: string };
  Conversation: { procedureId: string; runId: string };
};
