interface SafetyBannerProps {
  disclaimer?: string;
}

const DEFAULT_DISCLAIMER =
  'Research prototype only: ParkTwin estimates and simulations are non-diagnostic, hypothetical where labeled, and must not be used for primary diagnosis, prescribing, or clinical treatment decisions.';

export function SafetyBanner({ disclaimer }: SafetyBannerProps) {
  return (
    <div className="safety-banner" role="region" aria-label="Non-diagnostic safety notice">
      <span className="safety-badge" aria-hidden="true">
        ! NON-DIAGNOSTIC PROTOTYPE
      </span>
      <p>{disclaimer ?? DEFAULT_DISCLAIMER}</p>
    </div>
  );
}
