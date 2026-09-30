-- Annonce + dernière évaluation + dernier avis : alimente l'interface.
SELECT
  l.*,
  e.evaluated_at, e.config_version, e.exclusion_reason, e.exclusion_detail, e.km_per_year, e.distance_km,
  e.market_price_eur, e.resale_price_eur, e.negotiation_discount_eur, e.comparables_count, e.comparables_widened,
  e.reliability, e.fees_eur, e.transport_eur, e.margin_eur, e.alert_level,
  CASE
    WHEN e.alert_level IS NOT NULL THEN 'alerte'
    WHEN e.exclusion_reason = 'cote_indisponible' THEN 'sans_cote'
    WHEN e.exclusion_reason IS NOT NULL THEN 'exclue'
    WHEN e.margin_eur IS NOT NULL THEN 'sous_seuil'
    ELSE 'non_evaluee'
  END AS statut,
  f.status AS feedback_status, f.purchase_price_eur, f.created_at AS feedback_at
FROM `${project}.${dataset}.listings` AS l
LEFT JOIN `${project}.${dataset}.v_latest_evaluation` AS e USING (source, listing_id)
LEFT JOIN `${project}.${dataset}.v_latest_feedback` AS f USING (source, listing_id)
