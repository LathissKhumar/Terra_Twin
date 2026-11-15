import { EvidencePassportReport } from "@/features/evidence-passport/evidence-passport-report";

export default async function CandidatePassportPage({ params }: { params: Promise<{ candidateId: string }> }) {
  const { candidateId } = await params;
  return <EvidencePassportReport key={candidateId} candidateId={candidateId} />;
}
