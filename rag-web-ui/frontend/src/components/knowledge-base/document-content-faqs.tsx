"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useToast } from "@/components/ui/use-toast";
import { api, ApiError } from "@/lib/api";
import { Check, Loader2, MessageSquare, X } from "lucide-react";
import { cn } from "@/lib/utils";

interface DocumentContent {
  id: number;
  document_id: number;
  raw_text: string;
  content_length: number | null;
  extracted_at: string | null;
}

interface FAQ {
  id: number;
  document_id: number;
  question: string;
  answer: string;
  feedback_status: "pending" | "correct" | "incorrect";
  corrected_answer: string | null;
  confidence_score: number | null;
}

interface DocumentContentFaqsProps {
  knowledgeBaseId: number;
  documentId: number;
  documentName?: string;
  className?: string;
  hideDocumentTitle?: boolean;
  onFaqsLoaded?: (
    documentId: number,
    stats: {
      total: number;
      pending: number;
      correct: number;
      incorrect: number;
    }
  ) => void;
}

export function DocumentContentFaqs({
  knowledgeBaseId,
  documentId,
  documentName,
  className,
  hideDocumentTitle = false,
  onFaqsLoaded,
}: DocumentContentFaqsProps) {
  const { toast } = useToast();
  const [content, setContent] = useState<DocumentContent | null>(null);
  const [faqs, setFaqs] = useState<FAQ[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeCorrectionId, setActiveCorrectionId] = useState<number | null>(
    null
  );
  const [correctionText, setCorrectionText] = useState("");
  const [submittingId, setSubmittingId] = useState<number | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [contentData, faqData] = await Promise.all([
        api.get(
          `/api/knowledge-base/${knowledgeBaseId}/documents/${documentId}/content`
        ),
        api.get(
          `/api/knowledge-base/${knowledgeBaseId}/documents/${documentId}/faqs`
        ),
      ]);
      setContent(contentData);
      setFaqs(faqData);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setError(
          "Extracted content and FAQs are not ready yet. Processing may still be in progress."
        );
      } else {
        setError(
          err instanceof ApiError ? err.message : "Failed to load document review data"
        );
      }
    } finally {
      setLoading(false);
    }
  }, [documentId, knowledgeBaseId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    setActiveCorrectionId(null);
    setCorrectionText("");
    setSubmittingId(null);
  }, [documentId]);

  useEffect(() => {
    if (loading || error || !onFaqsLoaded) return;
    onFaqsLoaded(documentId, {
      total: faqs.length,
      pending: faqs.filter((f) => f.feedback_status === "pending").length,
      correct: faqs.filter((f) => f.feedback_status === "correct").length,
      incorrect: faqs.filter((f) => f.feedback_status === "incorrect").length,
    });
  }, [documentId, loading, error, faqs, onFaqsLoaded]);

  const submitFeedback = async (
    faqId: number,
    feedbackType: "correct" | "incorrect",
    correctedAnswer?: string
  ) => {
    setSubmittingId(faqId);
    try {
      const updatedFaq = await api.post(
        `/api/knowledge-base/${knowledgeBaseId}/documents/${documentId}/faqs/${faqId}/feedback`,
        {
          feedback_type: feedbackType,
          corrected_answer: correctedAnswer,
        }
      );
      setFaqs((prev) =>
        prev.map((faq) => (faq.id === faqId ? { ...faq, ...updatedFaq } : faq))
      );
      toast({
        title: feedbackType === "correct" ? "Marked as correct" : "Feedback saved",
        description:
          feedbackType === "correct"
            ? "This FAQ has been verified."
            : "Your corrected answer has been recorded.",
      });
      setActiveCorrectionId(null);
      setCorrectionText("");
    } catch (err) {
      toast({
        title: "Feedback failed",
        description:
          err instanceof ApiError ? err.message : "Something went wrong",
        variant: "destructive",
      });
    } finally {
      setSubmittingId(null);
    }
  };

  const wordCount = content?.raw_text
    ? content.raw_text.trim().split(/\s+/).filter(Boolean).length
    : 0;

  if (loading) {
    return (
      <Card className={cn("p-6", className)}>
        <div className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          {documentName
            ? `Loading FAQs for ${documentName}...`
            : "Loading extracted content and FAQs..."}
        </div>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className={cn("p-6 space-y-3", className)}>
        <p className="text-sm text-muted-foreground">{error}</p>
        <Button variant="outline" size="sm" onClick={fetchData}>
          Retry
        </Button>
      </Card>
    );
  }

  return (
    <div className={cn("space-y-6", className)}>
      {documentName && !hideDocumentTitle && (
        <h3 className="text-lg font-medium">{documentName}</h3>
      )}

      <div className="space-y-3 max-h-[50vh] overflow-y-auto pr-1">
        <div className="flex items-center justify-between">
          <h4 className="text-base font-medium">Auto-generated FAQs</h4>
          <Badge variant="outline">{faqs.length} items</Badge>
        </div>

        {faqs.length === 0 ? (
          <Card className="p-4 text-sm text-muted-foreground">
            No FAQs were generated for this document.
          </Card>
        ) : (
          faqs.map((faq) => (
            <Card key={faq.id} className="p-4 space-y-3">
              <div className="flex items-start justify-between gap-3">
                <div className="space-y-2 flex-1">
                  <p className="font-medium">{faq.question}</p>
                  <p className="text-sm text-muted-foreground">{faq.answer}</p>
                  {faq.feedback_status === "incorrect" && faq.corrected_answer && (
                    <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm dark:border-amber-900 dark:bg-amber-950/30">
                      <span className="font-medium">Corrected answer: </span>
                      {faq.corrected_answer}
                    </div>
                  )}
                </div>
                <Badge
                  variant={
                    faq.feedback_status === "correct"
                      ? "default"
                      : faq.feedback_status === "incorrect"
                        ? "destructive"
                        : "secondary"
                  }
                >
                  {faq.feedback_status}
                </Badge>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant={faq.feedback_status === "correct" ? "default" : "outline"}
                  loading={submittingId === faq.id}
                  disabled={submittingId === faq.id}
                  onClick={() => submitFeedback(faq.id, "correct")}
                >
                  <Check className="mr-1 h-3.5 w-3.5" />
                  Correct
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant={
                    faq.feedback_status === "incorrect" ? "destructive" : "outline"
                  }
                  disabled={submittingId === faq.id}
                  onClick={() => {
                    setActiveCorrectionId(faq.id);
                    setCorrectionText(faq.corrected_answer || "");
                  }}
                >
                  <X className="mr-1 h-3.5 w-3.5" />
                  Incorrect
                </Button>
              </div>

              {activeCorrectionId === faq.id && (
                <div className="flex items-start gap-2 rounded-lg border bg-muted/30 p-3">
                  <MessageSquare className="mt-2 h-4 w-4 shrink-0 text-muted-foreground" />
                  <div className="flex-1 space-y-2">
                    <textarea
                      value={correctionText}
                      onChange={(e) => setCorrectionText(e.target.value)}
                      rows={3}
                      placeholder="Enter the correct answer..."
                      className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    />
                    <div className="flex gap-2">
                      <Button
                        type="button"
                        size="sm"
                        disabled={
                          submittingId === faq.id || !correctionText.trim()
                        }
                        loading={submittingId === faq.id}
                        loadingText="Saving..."
                        onClick={() =>
                          submitFeedback(faq.id, "incorrect", correctionText.trim())
                        }
                      >
                        Save correction
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          setActiveCorrectionId(null);
                          setCorrectionText("");
                        }}
                      >
                        Cancel
                      </Button>
                    </div>
                  </div>
                </div>
              )}
            </Card>
          ))
        )}
      </div>

      <Accordion type="single" collapsible>
        <AccordionItem value="content">
          <AccordionTrigger>
            <div className="flex items-center gap-2">
              <span>Extracted Content</span>
              <Badge variant="secondary">
                {wordCount.toLocaleString()} words
              </Badge>
            </div>
          </AccordionTrigger>
          <AccordionContent>
            <div className="max-h-[320px] overflow-y-auto rounded-lg border bg-muted/40 p-4">
              <pre className="whitespace-pre-wrap text-sm leading-relaxed">
                {content?.raw_text}
              </pre>
            </div>
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </div>
  );
}
