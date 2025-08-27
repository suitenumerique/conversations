declare module '*.json' {
  const value: Record<string, unknown>;
  export default value;
}

declare module '@/assets/lotties/*' {
  const value: Record<string, unknown>;
  export default value;
}
