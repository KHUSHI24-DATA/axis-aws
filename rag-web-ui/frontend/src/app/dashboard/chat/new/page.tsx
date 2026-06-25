"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import DashboardLayout from "@/components/layout/dashboard-layout";
import { Button } from "@/components/ui/button";
import {
  FormLoadingOverlay,
  PageLoading,
} from "@/components/ui/loading-indicator";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/ui/use-toast";
import { Plus } from "lucide-react";

interface KnowledgeBase {
  id: number;
  name: string;
  description: string;
}

export default function NewChatPage() {
  const router = useRouter();
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [selectedKB, setSelectedKB] = useState<number | null>(null);
  const [title, setTitle] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const { toast } = useToast();

  useEffect(() => {
    fetchKnowledgeBases();
  }, []);

  const fetchKnowledgeBases = async () => {
    try {
      const data = await api.get("/api/knowledge-base");
      setKnowledgeBases(data);
    } catch (error) {
      console.error("Failed to fetch knowledge bases:", error);
      if (error instanceof ApiError) {
        toast({
          title: "Error",
          description: error.message,
          variant: "destructive",
        });
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!selectedKB) {
      setError("Please select a knowledge base");
      return;
    }

    setError("");
    setIsSubmitting(true);

    try {
      const data = await api.post("/api/chat/create", {
        title,
        knowledge_base_ids: [selectedKB],
      });

      router.push(`/dashboard/chat/${data.id}`);
    } catch (error) {
      console.error("Failed to create chat:", error);
      if (error instanceof ApiError) {
        setError(error.message);
        toast({
          title: "Error",
          description: error.message,
          variant: "destructive",
        });
      } else {
        setError("Failed to create chat");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isLoading) {
    return (
      <DashboardLayout>
        <PageLoading message="Loading knowledge bases..." />
      </DashboardLayout>
    );
  }

  if (knowledgeBases.length === 0) {
    return (
      <DashboardLayout>
        <div className="max-w-2xl mx-auto text-center py-16">
          <h2 className="text-3xl font-bold tracking-tight mb-4">
            No Knowledge Bases Found
          </h2>
          <p className="text-muted-foreground mb-8">
            You need to create at least one knowledge base before starting a
            chat.
          </p>
          <Button asChild>
            <Link href="/dashboard/knowledge">
              <Plus className="mr-2 h-4 w-4" />
              Create Knowledge Base
            </Link>
          </Button>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="max-w-2xl mx-auto space-y-8">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">Start New Chat</h2>
          <p className="text-muted-foreground">
            Select a knowledge base to chat with
          </p>
        </div>

        <form onSubmit={handleSubmit} className="relative space-y-6">
          {isSubmitting && <FormLoadingOverlay message="Starting chat..." />}

          <div className="space-y-2">
            <label
              htmlFor="title"
              className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
            >
              Chat Title
            </label>
            <input
              id="title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              type="text"
              required
              disabled={isSubmitting}
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
              placeholder="Enter chat title"
            />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">
              Knowledge Base
            </label>
            <div className="text-xs text-muted-foreground">
              Multiple selection coming soon...
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              {knowledgeBases.map((kb) => (
                <label
                  key={kb.id}
                  className={`group flex items-center space-x-3 rounded-lg border p-4 cursor-pointer transition-all duration-200 hover:shadow-md ${
                    selectedKB === kb.id
                      ? "border-primary bg-primary/5 shadow-sm"
                      : "hover:border-primary/50"
                  }`}
                >
                  <div className="relative flex items-center justify-center">
                    <input
                      type="radio"
                      name="knowledge-base"
                      disabled={isSubmitting}
                      className="peer h-4 w-4 shrink-0 rounded-full border border-primary text-primary focus:outline-none focus:ring-2 focus:ring-primary/20 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                      checked={selectedKB === kb.id}
                      onChange={() => setSelectedKB(kb.id)}
                    />
                  </div>
                  <div className="flex-1 space-y-1">
                    <p className="font-medium group-hover:text-primary transition-colors">
                      {kb.name}
                    </p>
                    <p className="text-sm text-muted-foreground line-clamp-2">
                      {kb.description || "No description provided"}
                    </p>
                  </div>
                </label>
              ))}
            </div>
          </div>

          {error && <div className="text-sm text-red-500">{error}</div>}

          <div className="flex justify-end space-x-4">
            <Button
              type="button"
              variant="outline"
              onClick={() => router.back()}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={!selectedKB}
              loading={isSubmitting}
              loadingText="Starting chat..."
            >
              Start Chat
            </Button>
          </div>
        </form>
      </div>
    </DashboardLayout>
  );
}
