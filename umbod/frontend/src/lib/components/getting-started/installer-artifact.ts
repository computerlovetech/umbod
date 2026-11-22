import { strToU8, zipSync } from 'fflate';
import { z } from 'zod';
import { normalizeInstallationUrl } from './installation-url';
import type { InstallationPlatform } from './plugin-installation-state.svelte';

const artifactSchema = z.string().min(1).max(128 * 1024);
const tokenSchema = z.string().regex(/^umbod_pat_v1_[0-9a-f]{32}_[A-Za-z0-9_-]{43}$/u);
const bashShebang = '#!/usr/bin/env bash\n';

export interface InstallerArtifactSource {
  read(url: string): Promise<string>;
}

export class BrowserInstallerArtifactSource implements InstallerArtifactSource {
  constructor(private readonly request: typeof fetch) {}

  async read(url: string): Promise<string> {
    const response = await this.request(url, { credentials: 'omit', redirect: 'error', cache: 'no-store' });
    if (!response.ok || !/^text\/plain(?:;|$)/iu.test(response.headers.get('content-type') ?? '')) {
      throw new Error('The installer download is unavailable.');
    }
    const stream = response.body?.getReader();
    if (!stream) throw new Error('The installer download is empty.');
    const decoder = new TextDecoder('utf-8', { fatal: true });
    let content = '';
    let size = 0;
    try {
      for (;;) {
        const { done, value } = await stream.read();
        if (done) return artifactSchema.parse(content + decoder.decode());
        size += value.byteLength;
        if (size > 128 * 1024) throw new Error('The installer download is too large.');
        content += decoder.decode(value, { stream: true });
      }
    } finally {
      await stream.cancel().catch((): void => {});
      stream.releaseLock();
    }
  }
}

export function supportsTelemetry(artifact: string, platform: InstallationPlatform): boolean {
  return platform === 'windows'
    ? artifact.startsWith('& {\n') && artifact.includes('$UmbodTelemetryPayload')
    : artifact.startsWith(bashShebang) && artifact.includes('umbod_telemetry_payload');
}

export function validateTelemetryEndpoint(endpoint: string): string {
  const normalized = normalizeInstallationUrl(endpoint);
  if (endpoint.length > 2048 || !endpoint.endsWith('/v1/logs') || !/^[A-Za-z0-9:/._~!&'()*+,;=@%\[\]-]+$/u.test(endpoint) || /%[01][0-9a-f]|%7f|%(?![0-9a-f]{2})/iu.test(endpoint)) {
    throw new Error('The telemetry endpoint is not supported.');
  }
  return normalized;
}

export function privateTelemetryInstaller(artifact: string, platform: InstallationPlatform, endpoint: string, token: string): Blob {
  if (!tokenSchema.safeParse(token).success) throw new Error('The telemetry token format is not supported.');
  const bytes = new TextEncoder().encode(JSON.stringify({ endpoint, token }));
  const encoded = btoa(Array.from(bytes, (byte: number): string => String.fromCharCode(byte)).join(''));
  const windows = platform === 'windows';
  const content = windows
    ? `$TelemetryFile = Join-Path $PSScriptRoot 'umbod-telemetry.txt'\ntry {\n    $Source = Get-Item -ErrorAction Stop -LiteralPath $TelemetryFile\n    if ($Source.PSIsContainer -or ($Source.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $Source.Length -gt 8192) { throw 'Invalid telemetry file' }\n    $UmbodTelemetryPayload = [IO.File]::ReadAllText($TelemetryFile).TrimEnd([char]10)\n    if (-not $UmbodTelemetryPayload) { throw 'Empty telemetry file' }\n} catch {\n    Write-Error 'Could not read the telemetry file next to the installer.'\n    exit 1\n}\n` + artifact + '\nRemove-Variable UmbodTelemetryPayload -ErrorAction SilentlyContinue\n'
    : bashShebang + `set +vx\ntelemetry_file=\"\${BASH_SOURCE[0]%/*}/umbod-telemetry.txt\"\nif [[ \"\${BASH_SOURCE[0]}\" != */* ]]; then telemetry_file=./umbod-telemetry.txt; fi\nif [[ ! -f \"$telemetry_file\" || -L \"$telemetry_file\" ]] || ! IFS= read -r -n 8193 umbod_telemetry_payload <\"$telemetry_file\" || [[ -z \"$umbod_telemetry_payload\" ]]; then\n    printf '%s\\n' 'Could not read the telemetry file next to the installer.' >&2\n    exit 1\nfi\n` + artifact.slice(bashShebang.length);
  const archive = zipSync({
    [windows ? 'umbod-install.ps1' : 'umbod-install.sh']: strToU8(content),
    'umbod-telemetry.txt': [strToU8(encoded + '\n'), { os: 3, attrs: 0o100600 << 16 }]
  });
  return new Blob([new Uint8Array(archive)], { type: 'application/zip' });
}
