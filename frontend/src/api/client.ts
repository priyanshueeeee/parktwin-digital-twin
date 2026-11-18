import type {
  ApiEnvelope,
  ApiErrorEnvelope,
  AuditTrailData,
  FieldValidationError,
  ObservationsData,
  ReadinessData,
  RecomputePayload,
  ScenarioListItem,
  SimulationData,
  SimulationPayload,
  TrajectoryData,
  TwinCreatePayload,
  TwinListData,
  TwinRecord,
  TwinStatusUpdatePayload,
  TwinUpdatePayload,
} from './types';

export class ParkTwinApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string;
  readonly fields: FieldValidationError[];

  constructor(params: {
    status: number;
    code: string;
    message: string;
    requestId: string;
    fields?: FieldValidationError[];
  }) {
    super(params.message);
    this.name = 'ParkTwinApiError';
    this.status = params.status;
    this.code = params.code;
    this.requestId = params.requestId;
    this.fields = params.fields ?? [];
  }
}

function generateIdempotencyKey(prefix: string): string {
  const rand =
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  return `${prefix}-${rand}`;
}

export interface ParkTwinClient {
  getReady(): Promise<ApiEnvelope<ReadinessData>>;
  listTwins(): Promise<ApiEnvelope<TwinListData>>;
  createTwin(
    payload: TwinCreatePayload,
  ): Promise<ApiEnvelope<{ twin: TwinRecord; disclaimer: string }>>;
  updateTwin(
    payload: TwinUpdatePayload,
  ): Promise<ApiEnvelope<{ twin: TwinRecord; observation_id: string; disclaimer: string }>>;
  getTrajectory(
    twinId: string,
    options?: {
      series?: 'all' | 'observed' | 'estimated';
      startTime?: string;
      endTime?: string;
      scenarioId?: string;
    },
  ): Promise<ApiEnvelope<TrajectoryData>>;
  simulate(twinId: string, payload: SimulationPayload): Promise<ApiEnvelope<SimulationData>>;
  listScenarios(
    twinId: string,
  ): Promise<ApiEnvelope<{ twin_id: string; scenarios: ScenarioListItem[]; disclaimer: string }>>;
  listObservations(twinId: string): Promise<ApiEnvelope<ObservationsData>>;
  listAuditEvents(twinId: string): Promise<ApiEnvelope<AuditTrailData>>;
  updateTwinStatus(
    twinId: string,
    payload: TwinStatusUpdatePayload,
  ): Promise<ApiEnvelope<{ twin: TwinRecord; previous_status: string; reason: string }>>;
  recomputeTwin(
    twinId: string,
    payload: RecomputePayload,
  ): Promise<ApiEnvelope<{ twin: TwinRecord; reestimated_observations: number }>>;
  exportTwin(twinId: string, format: 'json' | 'csv', scenarioId?: string): Promise<string>;
}

export class HttpParkTwinClient implements ParkTwinClient {
  private readonly baseUrl: string;
  private readonly apiKey: string;

  constructor(
    baseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000',
    apiKey = import.meta.env.VITE_API_KEY ?? 'dev-clinician-key',
  ) {
    this.baseUrl = baseUrl.replace(/\/+$/, '');
    this.apiKey = apiKey;
  }

  private async request<T>(
    path: string,
    init: RequestInit & { idempotencyKey?: string } = {},
  ): Promise<ApiEnvelope<T>> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'X-API-Key': this.apiKey,
      ...(init.headers as Record<string, string> | undefined),
    };
    if (init.idempotencyKey) {
      headers['Idempotency-Key'] = init.idempotencyKey;
    }

    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}${path}`, {
        ...init,
        headers,
      });
    } catch {
      throw new ParkTwinApiError({
        status: 0,
        code: 'NETWORK_ERROR',
        message: 'Unable to reach the ParkTwin API service. Check that the backend server is running.',
        requestId: 'client-network-error',
      });
    }

    const requestIdHeader = response.headers.get('X-Request-ID') ?? 'unknown';
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      throw new ParkTwinApiError({
        status: response.status,
        code: 'INVALID_RESPONSE',
        message: `Server returned non-JSON response (HTTP ${response.status}).`,
        requestId: requestIdHeader,
      });
    }

    if (!response.ok) {
      const errBody = body as Partial<ApiErrorEnvelope>;
      throw new ParkTwinApiError({
        status: response.status,
        code: errBody.error?.code ?? `HTTP_${response.status}`,
        message: errBody.error?.message ?? 'Request failed.',
        requestId: errBody.request_id ?? requestIdHeader,
        fields: errBody.error?.fields ?? [],
      });
    }

    return body as ApiEnvelope<T>;
  }

  getReady(): Promise<ApiEnvelope<ReadinessData>> {
    return this.request<ReadinessData>('/ready', { method: 'GET' });
  }

  listTwins(): Promise<ApiEnvelope<TwinListData>> {
    return this.request<TwinListData>('/twins', { method: 'GET' });
  }

  createTwin(
    payload: TwinCreatePayload,
  ): Promise<ApiEnvelope<{ twin: TwinRecord; disclaimer: string }>> {
    return this.request('/twin/create', {
      method: 'POST',
      body: JSON.stringify(payload),
      idempotencyKey: generateIdempotencyKey('ui-create'),
    });
  }

  updateTwin(
    payload: TwinUpdatePayload,
  ): Promise<ApiEnvelope<{ twin: TwinRecord; observation_id: string; disclaimer: string }>> {
    return this.request('/twin/update', {
      method: 'POST',
      body: JSON.stringify(payload),
      idempotencyKey: generateIdempotencyKey('ui-update'),
    });
  }

  getTrajectory(
    twinId: string,
    options?: {
      series?: 'all' | 'observed' | 'estimated';
      startTime?: string;
      endTime?: string;
      scenarioId?: string;
    },
  ): Promise<ApiEnvelope<TrajectoryData>> {
    const params = new URLSearchParams();
    if (options?.series) params.set('series', options.series);
    if (options?.startTime) params.set('start_time', options.startTime);
    if (options?.endTime) params.set('end_time', options.endTime);
    if (options?.scenarioId) params.set('scenario_id', options.scenarioId);
    const qs = params.toString();
    return this.request<TrajectoryData>(`/twin/${encodeURIComponent(twinId)}/trajectory${qs ? `?${qs}` : ''}`, {
      method: 'GET',
    });
  }

  simulate(twinId: string, payload: SimulationPayload): Promise<ApiEnvelope<SimulationData>> {
    return this.request<SimulationData>(`/twin/${encodeURIComponent(twinId)}/simulate`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  listScenarios(
    twinId: string,
  ): Promise<ApiEnvelope<{ twin_id: string; scenarios: ScenarioListItem[]; disclaimer: string }>> {
    return this.request(`/twin/${encodeURIComponent(twinId)}/scenarios`, { method: 'GET' });
  }

  listObservations(twinId: string): Promise<ApiEnvelope<ObservationsData>> {
    return this.request<ObservationsData>(`/twin/${encodeURIComponent(twinId)}/observations`, {
      method: 'GET',
    });
  }

  listAuditEvents(twinId: string): Promise<ApiEnvelope<AuditTrailData>> {
    return this.request<AuditTrailData>(`/twin/${encodeURIComponent(twinId)}/audit`, {
      method: 'GET',
    });
  }

  updateTwinStatus(
    twinId: string,
    payload: TwinStatusUpdatePayload,
  ): Promise<ApiEnvelope<{ twin: TwinRecord; previous_status: string; reason: string }>> {
    return this.request(`/twin/${encodeURIComponent(twinId)}/status`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
  }

  recomputeTwin(
    twinId: string,
    payload: RecomputePayload,
  ): Promise<ApiEnvelope<{ twin: TwinRecord; reestimated_observations: number }>> {
    return this.request(`/twin/${encodeURIComponent(twinId)}/recompute`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async exportTwin(twinId: string, format: 'json' | 'csv', scenarioId?: string): Promise<string> {
    const params = new URLSearchParams({ format });
    if (scenarioId) params.set('scenario_id', scenarioId);
    const resp = await fetch(
      `${this.baseUrl}/twin/${encodeURIComponent(twinId)}/export?${params.toString()}`,
      {
        method: 'GET',
        headers: { 'X-API-Key': this.apiKey },
      },
    );
    if (!resp.ok) {
      throw new ParkTwinApiError({
        status: resp.status,
        code: `HTTP_${resp.status}`,
        message: 'Failed to export twin trajectory.',
        requestId: resp.headers.get('X-Request-ID') ?? 'unknown',
      });
    }
    return resp.text();
  }
}
