import { groupIdSchema } from '$lib/admin/groups/domain/schemas';

export class GroupRegistrationState {
  open = $state(false);
  groupId = $state('');
  pending = $state(false);
  error = $state('');
  constructor(private readonly register: (groupId: string) => Promise<void>, private readonly onregistered: (groupId: string) => void) {}
  get valid(): boolean { return groupIdSchema.safeParse(this.groupId).success; }
  show = (): void => { this.groupId = ''; this.error = ''; this.open = true; };
  edit = (value: string): void => { if (!this.pending) this.groupId = value; };
  cancel = (): void => { if (!this.pending) this.open = false; };
  submit = async (): Promise<void> => {
    if (!this.valid || this.pending) return;
    this.pending = true;
    this.error = '';
    const groupId = this.groupId;
    try {
      await this.register(groupId);
      this.onregistered(groupId);
      this.open = false;
    } catch {
      this.error = 'Group could not be registered. Try again.';
    } finally { this.pending = false; }
  };
}
