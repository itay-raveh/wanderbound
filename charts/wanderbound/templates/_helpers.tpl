{{- define "wanderbound.fullname" -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{- define "wanderbound.configName" -}}
{{- printf "%s-config" (include "wanderbound.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{- define "wanderbound.pvcName" -}}
{{- if .Values.persistence.existingClaim -}}
{{- .Values.persistence.existingClaim -}}
{{- else -}}
{{- printf "%s-app-data" (include "wanderbound.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end }}

{{- define "wanderbound.image" -}}
{{- $tag := default .Chart.AppVersion .Values.image.tag -}}
{{- printf "%s:%s" .Values.image.repository $tag -}}
{{- end }}

{{- define "wanderbound.selectorLabels" -}}
app: {{ include "wanderbound.fullname" . }}
{{- end }}

{{- define "wanderbound.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{ include "wanderbound.selectorLabels" . }}
{{- end }}

{{- define "wanderbound.containerSecurityContext" -}}
allowPrivilegeEscalation: false
capabilities:
  drop:
    - ALL
readOnlyRootFilesystem: true
runAsGroup: 999
runAsNonRoot: true
runAsUser: 999
seccompProfile:
  type: RuntimeDefault
{{- end }}
