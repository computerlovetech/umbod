import { error } from "@sveltejs/kit";
import { adminApi } from "$lib/admin/infrastructure/admin-api";
import { HttpError } from "$lib/admin/infrastructure/transport";
import type { InstanceConfigurationPageData } from "$lib/admin/instance-configuration";
import type { PageLoad } from "./$types";

export const load: PageLoad = async (
  event,
): Promise<InstanceConfigurationPageData> => {
  try {
    const configuration =
      await adminApi(event.fetch).instanceConfiguration.get();
    return configuration.groups.length === 0
      ? { status: "empty" }
      : { status: "ready", configuration };
  } catch (cause) {
    if (
      cause instanceof HttpError &&
      (cause.status === 401 || cause.status === 403)
    ) {
      throw error(cause.status, cause.statusText);
    }
    return {
      status: "failed",
      message: "Instance configuration could not be loaded",
      retryLabel: "Try again",
    };
  }
};
