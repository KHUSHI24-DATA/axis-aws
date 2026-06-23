"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDistanceToNow } from "date-fns";
import { api, ApiError } from "@/lib/api";
import { FileIcon, defaultStyles } from "react-file-icon";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { DocumentContentFaqs } from "@/components/knowledge-base/document-content-faqs";
import { FileText } from "lucide-react";

interface Document {
  id: number;
  file_name: string;
  file_path: string;
  file_size: number;
  content_type: string;
  created_at: string;
  processing_tasks: Array<{
    id: number;
    status: string;
    error_message: string | null;
  }>;
}

interface KnowledgeBase {
  id: number;
  name: string;
  description: string;
  documents: Document[];
}

interface DocumentListProps {
  knowledgeBaseId: number;
}

export function DocumentList({ knowledgeBaseId }: DocumentListProps) {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reviewDocument, setReviewDocument] = useState<Document | null>(null);

  useEffect(() => {
    const fetchDocuments = async () => {
      try {
        const data = await api.get(`/api/knowledge-base/${knowledgeBaseId}`);
        setDocuments(data.documents);
      } catch (error) {
        if (error instanceof ApiError) {
          setError(error.message);
        } else {
          setError("Failed to fetch documents");
        }
      } finally {
        setLoading(false);
      }
    };

    fetchDocuments();
  }, [knowledgeBaseId]);

  if (loading) {
    return (
      <div className="flex justify-center items-center p-8">
        <div className="space-y-4">
          <div className="w-8 h-8 border-4 border-primary/30 border-t-primary rounded-full animate-spin mx-auto"></div>
          <p className="text-muted-foreground animate-pulse">
            Loading documents...
          </p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex justify-center items-center p-8">
        <p className="text-destructive">{error}</p>
      </div>
    );
  }

  if (documents.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] p-8">
        <div className="flex flex-col items-center max-w-[420px] text-center space-y-6">
          <div className="w-20 h-20 rounded-full bg-muted flex items-center justify-center">
            <FileText className="w-10 h-10 text-muted-foreground" />
          </div>
          <div className="space-y-2">
            <h3 className="text-xl font-semibold">No documents yet</h3>
            <p className="text-muted-foreground">
              Upload your first document to start building your knowledge base.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Size</TableHead>
            <TableHead>Created</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Review</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {documents.map((doc) => {
            const isCompleted =
              doc.processing_tasks.length > 0 &&
              doc.processing_tasks[0].status === "completed";

            return (
              <TableRow key={doc.id}>
                <TableCell className="font-medium">
                  <div className="flex items-center gap-2">
                    <div className="w-6 h-6">
                      {doc.content_type.toLowerCase().includes("pdf") ? (
                        <FileIcon extension="pdf" {...defaultStyles.pdf} />
                      ) : doc.content_type.toLowerCase().includes("doc") ? (
                        <FileIcon extension="doc" {...defaultStyles.docx} />
                      ) : doc.content_type.toLowerCase().includes("txt") ? (
                        <FileIcon extension="txt" {...defaultStyles.txt} />
                      ) : doc.content_type.toLowerCase().includes("md") ? (
                        <FileIcon extension="md" {...defaultStyles.md} />
                      ) : (
                        <FileIcon
                          extension={doc.file_name.split(".").pop() || ""}
                          color="#E2E8F0"
                          labelColor="#94A3B8"
                        />
                      )}
                    </div>
                    {doc.file_name}
                  </div>
                </TableCell>
                <TableCell>{(doc.file_size / 1024 / 1024).toFixed(2)} MB</TableCell>
                <TableCell>
                  {formatDistanceToNow(new Date(doc.created_at), {
                    addSuffix: true,
                  })}
                </TableCell>
                <TableCell>
                  {doc.processing_tasks.length > 0 && (
                    <Badge
                      variant={
                        doc.processing_tasks[0].status === "completed"
                          ? "secondary"
                          : doc.processing_tasks[0].status === "failed"
                            ? "destructive"
                            : "default"
                      }
                    >
                      {doc.processing_tasks[0].status}
                    </Badge>
                  )}
                </TableCell>
                <TableCell className="text-right">
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={!isCompleted}
                    onClick={() => setReviewDocument(doc)}
                  >
                    Content & FAQs
                  </Button>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>

      <Dialog
        open={reviewDocument != null}
        onOpenChange={(open) => !open && setReviewDocument(null)}
      >
        <DialogContent className="max-w-4xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Extracted Content & FAQs</DialogTitle>
            <DialogDescription>
              {reviewDocument?.file_name}
            </DialogDescription>
          </DialogHeader>
          {reviewDocument && (
            <DocumentContentFaqs
              knowledgeBaseId={knowledgeBaseId}
              documentId={reviewDocument.id}
              documentName={reviewDocument.file_name}
            />
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
