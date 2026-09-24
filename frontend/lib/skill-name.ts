/**
 * A skill's name as people write it. Jobs store skills normalized to lower case ("python",
 * "a/b testing"), while a gap reads the job's own casing ("PyTorch"), so one skill showed two ways
 * across Analytics. Every skill name on a chart, a bar or a gap row goes through here.
 *
 * A known name takes its usual form whatever case it arrives in; an unknown name a person already cased
 * keeps that casing; an unknown lower-case name gets its acronyms upper-cased and its first letter
 * capitalized. No imports: `node --test` loads this file as it is.
 */
const KNOWN: Record<string, string> = {
  pytorch: "PyTorch",
  tensorflow: "TensorFlow",
  mlflow: "MLflow",
  dbt: "dbt",
  "scikit-learn": "scikit-learn",
  pandas: "pandas",
  numpy: "NumPy",
  pyspark: "PySpark",
  javascript: "JavaScript",
  typescript: "TypeScript",
  postgresql: "PostgreSQL",
  mysql: "MySQL",
  mongodb: "MongoDB",
  bigquery: "BigQuery",
  dynamodb: "DynamoDB",
  graphql: "GraphQL",
  github: "GitHub",
  gitlab: "GitLab",
  openai: "OpenAI",
  langchain: "LangChain",
  xgboost: "XGBoost",
  "node.js": "Node.js",
  "machine learning": "Machine learning",
};

const ACRONYMS = new Set([
  "a/b", "ai", "api", "apis", "aws", "bi", "ci/cd", "crm", "css", "cuda", "erp", "etl", "gcp", "gpu",
  "html", "json", "kpi", "kpis", "llm", "llms", "ml", "mlops", "nlp", "ocr", "qa", "r", "rest", "saas",
  "sas", "spss", "sql", "ui", "ux",
]);

export function skillName(name: string): string {
  const known = KNOWN[name.trim().toLowerCase()];
  if (known) return known;
  if (/[A-Z]/.test(name)) return name;
  const words = name.split(" ").map((word) => (ACRONYMS.has(word) ? word.toUpperCase() : word));
  const text = words.join(" ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}
