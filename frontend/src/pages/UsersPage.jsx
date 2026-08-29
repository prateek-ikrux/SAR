import { useState } from "react";
import { Loader2, Trash2, UserPlus } from "lucide-react";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { errorMessage } from "@/lib/api";
import { useMe } from "@/hooks/useAuth";
import { useCreateUser, useDeleteUser, useUpdateUser, useUsers } from "@/hooks/useUsers";

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : "never";
}

export default function UsersPage() {
  const { data: me } = useMe();
  const { data: users, isPending } = useUsers();
  const createUser = useCreateUser();
  const updateUser = useUpdateUser();
  const deleteUser = useDeleteUser();

  const [form, setForm] = useState({ email: "", name: "", role: "recruiter" });
  const [pendingDelete, setPendingDelete] = useState(null);

  function submit(event) {
    event.preventDefault();
    createUser.mutate(form, {
      onSuccess: (user) => {
        toast.success(`${user.email} added. They sign in with a code sent to that address.`);
        setForm({ email: "", name: "", role: "recruiter" });
      },
      onError: (err) => toast.error(errorMessage(err, "Could not create the user.")),
    });
  }

  function toggleActive(user) {
    updateUser.mutate(
      { id: user.id, active: !user.active },
      {
        onSuccess: () =>
          toast.success(
            user.active
              ? `${user.email} deactivated. Their access stops on the next request.`
              : `${user.email} reactivated.`,
          ),
        onError: (err) => toast.error(errorMessage(err, "Could not update the user.")),
      },
    );
  }

  function confirmDelete() {
    const user = pendingDelete;
    setPendingDelete(null);
    deleteUser.mutate(user.id, {
      onSuccess: () => toast.success(`${user.email} deleted.`),
      onError: (err) => toast.error(errorMessage(err, "Could not delete the user.")),
    });
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Add a user</CardTitle>
          <CardDescription>
            There is no password to set. They sign in with a one-time code emailed to this address,
            so it must be a mailbox they can read.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
            <div className="min-w-56 flex-1 space-y-2">
              <Label htmlFor="new-email">Email</Label>
              <Input
                id="new-email"
                type="email"
                required
                placeholder="name@ikrux.com"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
              />
            </div>
            <div className="min-w-48 flex-1 space-y-2">
              <Label htmlFor="new-name">Name</Label>
              <Input
                id="new-name"
                required
                placeholder="Full name"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </div>
            <div className="w-40 space-y-2">
              <Label htmlFor="new-role">Role</Label>
              <Select value={form.role} onValueChange={(role) => setForm({ ...form, role })}>
                <SelectTrigger id="new-role" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="recruiter">Recruiter</SelectItem>
                  <SelectItem value="admin">Admin</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Button type="submit" disabled={createUser.isPending}>
              {createUser.isPending ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <UserPlus className="size-4" />
              )}
              Add user
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Users</CardTitle>
          <CardDescription>
            Deactivating takes effect on that person&apos;s next request — it is also the only way
            to cut off a token before its 24 hours are up.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isPending ? (
            <div className="space-y-2">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-10" />
              ))}
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Email</TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Last sign-in</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users?.map((user) => {
                  const isSelf = user.id === me?.id;
                  return (
                    <TableRow key={user.id}>
                      <TableCell className="font-medium">
                        {user.email}
                        {isSelf && (
                          <Badge variant="outline" className="ml-2 font-normal">
                            you
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell>{user.name}</TableCell>
                      <TableCell className="capitalize">{user.role}</TableCell>
                      <TableCell>
                        <Badge variant={user.active ? "secondary" : "destructive"}>
                          {user.active ? "active" : "inactive"}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {formatDate(user.last_login_at)}
                      </TableCell>
                      <TableCell className="space-x-1 text-right">
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={isSelf || updateUser.isPending}
                          onClick={() => toggleActive(user)}
                        >
                          {user.active ? "Deactivate" : "Activate"}
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="text-destructive"
                          disabled={isSelf}
                          onClick={() => setPendingDelete(user)}
                          aria-label={`Delete ${user.email}`}
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <AlertDialog open={Boolean(pendingDelete)} onOpenChange={(o) => !o && setPendingDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {pendingDelete?.email}?</AlertDialogTitle>
            <AlertDialogDescription>
              This cannot be undone. They lose access on their next request. To keep the account but
              stop access, deactivate it instead.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDelete}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
