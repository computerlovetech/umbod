{{- define "umbod.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- define "umbod.fullname" -}}
{{- if .Values.fullnameOverride }}{{ .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}{{ else }}{{ printf "%s-%s" .Release.Name (include "umbod.name" .) | trunc 63 | trimSuffix "-" }}{{ end }}
{{- end }}
{{- define "umbod.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
app.kubernetes.io/name: {{ include "umbod.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}
{{- define "umbod.selectorLabels" -}}
app.kubernetes.io/name: {{ include "umbod.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
{{- define "umbod.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}{{ default (include "umbod.fullname" .) .Values.serviceAccount.name }}{{ else }}{{ default "default" .Values.serviceAccount.name }}{{ end }}
{{- end }}
{{- define "umbod.claimName" -}}
{{- default (printf "%s-data" (include "umbod.fullname" .)) .Values.persistence.existingClaim }}
{{- end }}
