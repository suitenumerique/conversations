{{/*
Expand the name of the chart.
*/}}
{{- define "conversations.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "conversations.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "conversations.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
conversations.labels
*/}}
{{- define "conversations.labels" -}}
helm.sh/chart: {{ include "conversations.chart" . }}
{{ include "conversations.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "conversations.selectorLabels" -}}
app.kubernetes.io/name: {{ include "conversations.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
transform dictionary of environment variables
Usage : {{ include "conversations.env.transformDict" .Values.envVars }}

Example:
envVars:
  # Using simple strings as env vars
  ENV_VAR_NAME: "envVar value"
  # Using a value from a configMap
  ENV_VAR_FROM_CM:
    configMapKeyRef:
      name: cm-name
      key: "key_in_cm"
  # Using a value from a secret
  ENV_VAR_FROM_SECRET:
    secretKeyRef:
      name: secret-name
      key: "key_in_secret"
*/}}
{{- define "conversations.env.transformDict" -}}
{{- range $key, $value := . }}
- name: {{ $key | quote }}
{{- if $value | kindIs "map" }}
  valueFrom: {{ $value | toYaml | nindent 4 }}
{{- else }}
  value: {{ $value | quote }}
{{- end }}
{{- end }}
{{- end }}


{{/*
conversations env vars
*/}}
{{- define "conversations.common.env" -}}
{{- $topLevelScope := index . 0 -}}
{{- $workerScope := index . 1 -}}
{{- include "conversations.env.transformDict" $workerScope.envVars -}}
{{- end }}

{{/*
Common labels

Requires array with top level scope and component name
*/}}
{{- define "conversations.common.labels" -}}
{{- $topLevelScope := index . 0 -}}
{{- $component := index . 1 -}}
{{- include "conversations.labels" $topLevelScope }}
app.kubernetes.io/component: {{ $component }}
{{- end }}

{{/*
Common selector labels

Requires array with top level scope and component name
*/}}
{{- define "conversations.common.selectorLabels" -}}
{{- $topLevelScope := index . 0 -}}
{{- $component := index . 1 -}}
{{- include "conversations.selectorLabels" $topLevelScope }}
app.kubernetes.io/component: {{ $component }}
{{- end }}

{{- define "conversations.probes.abstract" -}}
{{- if .exec -}}
exec:
{{- toYaml .exec | nindent 2 }}
{{- else if .tcpSocket -}}
tcpSocket:
{{- toYaml .tcpSocket | nindent 2 }}
{{- else -}}
httpGet:
  path: {{ .path }}
  port: {{ .targetPort }}
{{- end }}
initialDelaySeconds: {{ .initialDelaySeconds | eq nil | ternary 0 .initialDelaySeconds }}
timeoutSeconds: {{ .timeoutSeconds | eq nil | ternary 1 .timeoutSeconds }}
{{- end }}

{{/*
Full name for the backend

Requires top level scope
*/}}
{{- define "conversations.backend.fullname" -}}
{{ include "conversations.fullname" . }}-backend
{{- end }}

{{/*
Full name for the frontend

Requires top level scope
*/}}
{{- define "conversations.frontend.fullname" -}}
{{ include "conversations.fullname" . }}-frontend
{{- end }}

{{/*
Full name for the Posthog

Requires top level scope
*/}}
{{- define "conversations.posthog.fullname" -}}
{{ include "conversations.fullname" . }}-posthog
{{- end }}


{{/*
Usage : {{ include "conversations.secret.dockerconfigjson.name" (dict "fullname" (include "conversations.fullname" .) "imageCredentials" .Values.path.to.the.image1) }}
*/}}
{{- define "conversations.secret.dockerconfigjson.name" }}
{{- if (default (dict) .imageCredentials).name }}{{ .imageCredentials.name }}{{ else }}{{ .fullname | trunc 63 | trimSuffix "-" }}-dockerconfig{{ end -}}
{{- end }}

{{/*
Usage : {{ include "conversations.secret.dockerconfigjson" (dict "fullname" (include "conversations.fullname" .) "imageCredentials" .Values.path.to.the.image1) }}
*/}}
{{- define "conversations.secret.dockerconfigjson" }}
{{- if .imageCredentials -}}
apiVersion: v1
kind: Secret
metadata:
  name: {{ template "conversations.secret.dockerconfigjson.name" (dict "fullname" .fullname "imageCredentials" .imageCredentials) }}
  annotations:
    "helm.sh/hook": pre-install,pre-upgrade
    "helm.sh/hook-weight": "-5"
    "helm.sh/hook-delete-policy": before-hook-creation
type: kubernetes.io/dockerconfigjson
data:
  .dockerconfigjson: {{ template "conversations.secret.dockerconfigjson.data" .imageCredentials }}
{{- end -}}
{{- end }}

{{/*
Environment enabling the prometheus metrics on the backend container, and on it
only: the celery worker and beat serve no request, so their metrics would never
be read. A pod is only ever scraped over plain http (TLS ends at the ingress, and
a Prometheus of the cluster calls the pods themselves), so the path is also taken
out of the redirect to https. Each variable is skipped when backend.envVars sets
it: an explicit value wins. The bearer token (PROMETHEUS_API_KEY) is not set
here: it is a secret, given through backend.envVars.

Requires top level scope
*/}}
{{- define "conversations.backend.metrics.env" -}}
{{- if .Values.backend.metrics.enabled -}}
{{- $named := .Values.backend.envVars | default dict -}}
{{- range $variable := list "PROMETHEUS_METRICS_ENABLED" "PROMETHEUS_METRICS_SSL_REDIRECT_EXEMPT" -}}
{{- if not (hasKey $named $variable) }}
- name: {{ $variable | quote }}
  value: "True"
{{- end }}
{{- end }}
{{- end }}
{{- end }}

{{/*
The Secret a monitor reads the bearer token of a scrape from: the one named in
backend.metrics.apiKeySecret, or else the one PROMETHEUS_API_KEY is taken from in
backend.envVars. A token that comes from nowhere the Prometheus Operator can read
is refused at render time, rather than left to fail at scrape time with a 401.

Requires top level scope
*/}}
{{- define "conversations.metrics.apiKeySecret" -}}
{{- $ref := .Values.backend.metrics.apiKeySecret | default dict -}}
{{- if not $ref.name -}}
{{- $fromEnv := index (.Values.backend.envVars | default dict) "PROMETHEUS_API_KEY" -}}
{{- $ref = (kindIs "map" $fromEnv) | ternary $fromEnv dict -}}
{{- $ref = $ref.secretKeyRef | default dict -}}
{{- end -}}
{{- if not (and $ref.name $ref.key) -}}
{{- fail "a monitor scrapes with the bearer token of PROMETHEUS_API_KEY, which has to come from a Secret. Give it as a secretKeyRef in backend.envVars, or name the Secret in backend.metrics.apiKeySecret" -}}
{{- end -}}
name: {{ $ref.name | quote }}
key: {{ $ref.key | quote }}
{{- end }}

{{/*
The endpoint of a ServiceMonitor or a PodMonitor scraping the backend: its http
port, the /metrics path, the scrape settings of the monitor and the bearer token.

Requires a dict with "root" (top level scope) and "monitor" (the serviceMonitor
or podMonitor values)
*/}}
{{- define "conversations.metrics.endpoint" -}}
- port: http
  path: /metrics
  scheme: http
  {{- with .monitor.interval }}
  interval: {{ . }}
  {{- end }}
  {{- with .monitor.scrapeTimeout }}
  scrapeTimeout: {{ . }}
  {{- end }}
  honorLabels: {{ .monitor.honorLabels }}
  authorization:
    type: Bearer
    credentials:
      {{- include "conversations.metrics.apiKeySecret" .root | nindent 6 }}
  {{- with .monitor.relabelings }}
  relabelings:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  {{- with .monitor.metricRelabelings }}
  metricRelabelings:
    {{- toYaml . | nindent 4 }}
  {{- end }}
{{- end }}
