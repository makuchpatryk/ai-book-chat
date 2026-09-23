import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@libs/components/ui/alert";
import { Button } from "@libs/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@libs/components/ui/dialog";
import { cn } from "@libs/utils/utils";
import type { QuizOption, QuizQuestion } from "@libs/types";
import { useQuiz } from "../hooks/useQuiz";
import { useRegenerateQuiz } from "../hooks/useRegenerateQuiz";

const OPTIONS: QuizOption[] = ["A", "B", "C", "D"];

function optionText(question: QuizQuestion, option: QuizOption): string {
  return { A: question.option_a, B: question.option_b, C: question.option_c, D: question.option_d }[
    option
  ];
}

interface QuizModalProps {
  documentId: string;
  documentTitle: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function QuizModal({ documentId, documentTitle, open, onOpenChange }: QuizModalProps) {
  const { data: quiz } = useQuiz(documentId, open);
  const regenerate = useRegenerateQuiz();
  const [answers, setAnswers] = useState<(QuizOption | null)[]>(Array(10).fill(null));
  const [submitted, setSubmitted] = useState(false);

  // A freshly generated quiz has a new id — reset the in-progress attempt.
  useEffect(() => {
    setAnswers(Array(10).fill(null));
    setSubmitted(false);
  }, [quiz?.id]);

  const allAnswered = answers.every((a) => a !== null);
  const score = submitted
    ? quiz?.questions.filter((q, i) => answers[i] === q.correct_option).length
    : undefined;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-h-[85vh] overflow-y-auto sm:max-w-2xl"
        onInteractOutside={(e) => e.preventDefault()}
        onEscapeKeyDown={(e) => e.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle>Quiz: {documentTitle}</DialogTitle>
          <DialogDescription>
            {submitted
              ? `You scored ${score} / ${quiz?.questions.length ?? 10}.`
              : "Answer all questions, then submit for your score."}
          </DialogDescription>
        </DialogHeader>

        {(!quiz || quiz.status === "pending") && (
          <div className="flex items-center gap-2 py-8 justify-center text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            Generating quiz…
          </div>
        )}

        {quiz?.status === "failed" && (
          <Alert variant="destructive">
            <AlertTitle>Quiz generation failed</AlertTitle>
            <AlertDescription className="flex items-center justify-between gap-2">
              <span>{quiz.error_message || "Something went wrong."}</span>
              <Button
                size="sm"
                variant="outline"
                disabled={regenerate.isPending}
                onClick={() => regenerate.mutate(documentId)}
              >
                Try again
              </Button>
            </AlertDescription>
          </Alert>
        )}

        {quiz?.status === "ready" && (
          <div className="space-y-6">
            <div className="space-y-5">
              {quiz.questions.map((q, i) => (
                <fieldset key={q.position} className="space-y-2">
                  <legend className="text-sm font-medium">
                    {i + 1}. {q.question}
                  </legend>
                  <div className="grid gap-1.5" role="radiogroup">
                    {OPTIONS.map((option) => {
                      const selected = answers[i] === option;
                      const correct = submitted && option === q.correct_option;
                      const incorrect = submitted && selected && option !== q.correct_option;
                      return (
                        <button
                          key={option}
                          type="button"
                          role="radio"
                          aria-checked={selected}
                          disabled={submitted}
                          onClick={() =>
                            setAnswers((prev) => prev.map((a, idx) => (idx === i ? option : a)))
                          }
                          className={cn(
                            "text-left text-sm rounded-md border px-3 py-2 transition-colors",
                            selected && !submitted && "border-primary bg-accent",
                            !selected && !submitted && "border-border hover:bg-accent",
                            correct && "border-green-600 bg-green-600/10",
                            incorrect && "border-destructive bg-destructive/10",
                            submitted && !correct && !incorrect && "opacity-60"
                          )}
                        >
                          <span className="font-medium">{option}.</span> {optionText(q, option)}
                        </button>
                      );
                    })}
                  </div>
                </fieldset>
              ))}
            </div>

            <div className="flex justify-end gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={regenerate.isPending}
                onClick={() => regenerate.mutate(documentId)}
              >
                Regenerate
              </Button>
              {!submitted && (
                <Button size="sm" disabled={!allAnswered} onClick={() => setSubmitted(true)}>
                  Submit
                </Button>
              )}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
