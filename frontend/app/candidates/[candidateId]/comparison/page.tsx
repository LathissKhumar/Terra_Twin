import { CandidateComparison } from "@/features/analogue-discovery/candidate-comparison";

export default async function CandidateComparisonPage({ params }: { params: Promise<{ candidateId: string }> }) {
  const { candidateId } = await params;
  return <CandidateComparison candidateId={candidateId} />;
}
