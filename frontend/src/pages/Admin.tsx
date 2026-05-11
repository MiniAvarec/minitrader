import { useMemo } from "react";
import { Navigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ShieldCheck, Trash2 } from "lucide-react";
import { toast } from "sonner";
import {
  AdminUserRow,
  approveUser,
  listAdminUsers,
  rejectUser,
} from "@/api/client";
import { useAuth } from "@/auth";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export default function Admin() {
  const { me } = useAuth();
  const qc = useQueryClient();

  const users = useQuery({
    queryKey: ["admin-users"],
    queryFn: listAdminUsers,
    enabled: !!me?.is_admin,
  });

  const approve = useMutation({
    mutationFn: (id: number) => approveUser(id),
    onSuccess: () => {
      toast.success("User approved");
      qc.invalidateQueries({ queryKey: ["admin-users"] });
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || "Approve failed"),
  });

  const reject = useMutation({
    mutationFn: (id: number) => rejectUser(id),
    onSuccess: () => {
      toast.success("User rejected");
      qc.invalidateQueries({ queryKey: ["admin-users"] });
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || "Reject failed"),
  });

  const { pending, active } = useMemo(() => {
    const rows = users.data || [];
    return {
      pending: rows.filter((u) => !u.is_approved),
      active: rows.filter((u) => u.is_approved),
    };
  }, [users.data]);

  if (!me) return null;
  if (!me.is_admin) return <Navigate to="/" replace />;

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4" /> Pending approvals
          </CardTitle>
          <CardDescription>
            New registrations cannot sign in until you approve them here.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <UsersTable
            rows={pending}
            emptyText="No pending registrations."
            renderActions={(u) => (
              <div className="flex gap-2 justify-end">
                <Button
                  size="sm"
                  onClick={() => approve.mutate(u.id)}
                  disabled={approve.isPending}
                >
                  <Check className="mr-1 h-3 w-3" /> Approve
                </Button>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => {
                    if (confirm(`Reject ${u.email}? This deletes the account.`)) {
                      reject.mutate(u.id);
                    }
                  }}
                  disabled={reject.isPending}
                >
                  <Trash2 className="mr-1 h-3 w-3" /> Reject
                </Button>
              </div>
            )}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Approved users</CardTitle>
          <CardDescription>
            Active accounts. Removing an account here deletes all their data.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <UsersTable
            rows={active}
            emptyText="No approved users yet."
            renderActions={(u) => (
              <div className="flex justify-end">
                {u.id === me.id || u.is_admin ? (
                  <Badge variant="success">Admin</Badge>
                ) : (
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => {
                      if (
                        confirm(
                          `Remove ${u.email}? This deletes their keys, signals, and orders.`,
                        )
                      ) {
                        reject.mutate(u.id);
                      }
                    }}
                    disabled={reject.isPending}
                  >
                    <Trash2 className="mr-1 h-3 w-3" /> Remove
                  </Button>
                )}
              </div>
            )}
          />
        </CardContent>
      </Card>
    </div>
  );
}

function UsersTable({
  rows,
  emptyText,
  renderActions,
}: {
  rows: AdminUserRow[];
  emptyText: string;
  renderActions: (u: AdminUserRow) => React.ReactNode;
}) {
  if (rows.length === 0) {
    return (
      <p className="text-sm font-mono uppercase tracking-wider text-muted-foreground">
        {emptyText}
      </p>
    );
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Email</TableHead>
          <TableHead>Registered</TableHead>
          <TableHead>Status</TableHead>
          <TableHead className="text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((u) => (
          <TableRow key={u.id}>
            <TableCell className="font-mono">{u.email}</TableCell>
            <TableCell className="text-xs text-muted-foreground">
              {new Date(u.created_at).toLocaleString()}
            </TableCell>
            <TableCell>
              {u.is_admin ? (
                <Badge variant="success">Admin</Badge>
              ) : u.is_approved ? (
                <Badge>Approved</Badge>
              ) : (
                <Badge variant="destructive">Pending</Badge>
              )}
            </TableCell>
            <TableCell>{renderActions(u)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
