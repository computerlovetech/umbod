import type { CapabilityActivationStatus, ResourceActivationBatchResponse, ResourceCatalog } from '$lib/admin/capability-catalogs';
import { resourceActivationKey } from '$lib/admin/capability-catalogs';

export class DownstreamMcpResourceCatalogState {
  resources: ResourceCatalog['resources'];
  persistedStatuses: Record<string, CapabilityActivationStatus>;
  pending = $state(false);
  changedResources = $derived.by(() =>
    this.resources
      .filter((resource) => {
        const resourceId = resource.kind === 'resource' ? resource.uri : resource.uriTemplate;
        return this.persistedStatuses[resourceActivationKey(resource.kind, resourceId)] !== resource.activationStatus;
      })
      .map((resource) => {
        const resourceId = resource.kind === 'resource' ? resource.uri : resource.uriTemplate;
        return { resource_id: resourceId, kind: resource.kind, activation_status: resource.activationStatus };
      })
  );
  dirty = $derived(this.changedResources.length > 0);
  catalog = $derived.by((): ResourceCatalog => ({
    resources: this.resources,
    availableActions: this.resources.length ? ['activate'] : []
  }));

  constructor(catalog: ResourceCatalog) {
    this.resources = $state(catalog.resources);
    this.persistedStatuses = $state(Object.fromEntries(catalog.resources.map((resource) => {
      const resourceId = resource.kind === 'resource' ? resource.uri : resource.uriTemplate;
      return [resourceActivationKey(resource.kind, resourceId), resource.activationStatus];
    })));
  }

  setResourceActivation = (resourceId: string, kind: 'resource' | 'resource_template', enabled: boolean): void => {
    if (this.pending) return;
    const activationStatus: CapabilityActivationStatus = enabled ? 'enabled' : 'disabled';
    this.resources = this.resources.map((resource) => {
      const id = resource.kind === 'resource' ? resource.uri : resource.uriTemplate;
      return resource.kind === kind && id === resourceId ? { ...resource, activationStatus } : resource;
    });
  };

  activationEnabled = (resourceId: string, kind: 'resource' | 'resource_template'): boolean => {
    const resource = this.resources.find((candidate) =>
      candidate.kind === kind &&
      (candidate.kind === 'resource' ? candidate.uri : candidate.uriTemplate) === resourceId
    );
    return (resource?.activationStatus ?? 'disabled') === 'enabled';
  };

  beginSave = (): void => {
    this.pending = true;
  };

  finishSave = (response?: ResourceActivationBatchResponse): void => {
    if (response) {
      this.persistedStatuses = {
        ...this.persistedStatuses,
        ...Object.fromEntries(response.resources.map((resource) => [
          resourceActivationKey(resource.kind, resource.resource_id),
          resource.activation_status
        ]))
      };
      this.resources = this.resources.map((resource) => {
        const resourceId = resource.kind === 'resource' ? resource.uri : resource.uriTemplate;
        const key = resourceActivationKey(resource.kind, resourceId);
        return { ...resource, activationStatus: this.persistedStatuses[key] ?? resource.activationStatus };
      });
    }
    this.pending = false;
  };

  reconcileAuthoritative = (response: ResourceActivationBatchResponse): void => {
    this.persistedStatuses = Object.fromEntries(response.resources.map((resource) => [
      resourceActivationKey(resource.kind, resource.resource_id),
      resource.activation_status
    ]));
  };

  activationRequestJson = (): string => JSON.stringify(this.changedResources);
}
