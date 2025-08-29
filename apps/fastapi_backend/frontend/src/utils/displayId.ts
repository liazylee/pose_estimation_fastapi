// displayId.ts - Utility functions for unified player identification

export interface PersonData {
  track_id?: number;
  jersey_number?: string | number;
  jersey_confidence?: number;
  pose?: number[][];
  bbox?: number[];
  speed_kmh?: number;
}

/**
 * Get display ID that prioritizes jersey numbers over track IDs
 * @param person Person data object
 * @param confidenceThreshold Minimum confidence threshold for jersey numbers (default: 0.7)
 * @returns Display ID object with id, label, and type information
 */
export function getDisplayId(person: PersonData, confidenceThreshold: number = 0.7) {
  const trackId = person.track_id ?? 0;
  const jerseyNumber = person.jersey_number;
  const jerseyConfidence = person.jersey_confidence ?? 0;

  // Prioritize jersey number if available and confidence is high enough
  // Jersey number should be the REAL OCR-detected number (e.g., 10, 23, 7)
  if (jerseyNumber !== undefined && jerseyNumber !== null && jerseyConfidence >= confidenceThreshold) {
    const realJerseyNum = Number(jerseyNumber);
    return {
      id: `jersey_${realJerseyNum}`,
      displayValue: realJerseyNum, // Use the REAL jersey number from OCR
      label: `Jersey ${realJerseyNum}`,
      type: 'jersey' as const,
      confidence: jerseyConfidence,
      fallbackTrackId: trackId
    };
  }

  // Fall back to track ID - use the REAL ByteSort generated track ID
  return {
    id: `track_${trackId}`,
    displayValue: trackId, // Use the REAL track ID from ByteSort (not reindexed)
    label: `Track ${trackId}`,
    type: 'track' as const,
    confidence: 1.0,
    fallbackTrackId: trackId
  };
}

/**
 * Get consistent color for a display ID
 * @param displayId Display ID string (e.g., "jersey_10" or "track_15")
 * @param colors Array of colors to use
 * @returns Color string
 */
export function getDisplayIdColor(displayId: string, colors: string[]): string {
  // Extract numeric part for consistent color mapping
  const match = displayId.match(/(\d+)$/);
  const numericId = match ? parseInt(match[1], 10) : 0;
  return colors[Math.abs(numericId) % colors.length];
}

/**
 * Extract all unique display IDs from an array of persons
 * @param persons Array of person data
 * @param confidenceThreshold Minimum confidence threshold for jersey numbers
 * @returns Array of display ID objects sorted by type (jersey first) then by display value
 */
export function extractDisplayIds(persons: PersonData[], confidenceThreshold: number = 0.7) {
  const displayIdMap = new Map();
  
  persons.forEach(person => {
    const displayIdInfo = getDisplayId(person, confidenceThreshold);
    // Only add if the person has a valid track ID (> 0)
    if (displayIdInfo.fallbackTrackId > 0) {
      displayIdMap.set(displayIdInfo.id, displayIdInfo);
    }
  });
  
  // Sort by: Jersey numbers first (by real jersey number), then track IDs (by real track ID)
  return Array.from(displayIdMap.values()).sort((a, b) => {
    // Jersey numbers come first
    if (a.type === 'jersey' && b.type === 'track') return -1;
    if (a.type === 'track' && b.type === 'jersey') return 1;
    
    // Within the same type, sort by the real display value
    return a.displayValue - b.displayValue;
  });
}

/**
 * Check if two display IDs represent the same entity
 * @param id1 First display ID
 * @param id2 Second display ID  
 * @returns True if they represent the same entity
 */
export function isSameDisplayId(id1: string, id2: string): boolean {
  return id1 === id2;
}

/**
 * Convert legacy track ID to new display ID format for backward compatibility
 * @param trackId Legacy track ID number
 * @returns Display ID object
 */
export function trackIdToDisplayId(trackId: number) {
  return {
    id: `track_${trackId}`,
    displayValue: trackId,
    label: `Track ${trackId}`,
    type: 'track' as const,
    confidence: 1.0,
    fallbackTrackId: trackId
  };
}