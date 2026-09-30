-- Candidats comparables : même marque, modèle, carburant et boîte, vus dans la fenêtre,
-- bornes larges (année ±2, ±40 000 km). La sélection stricte puis élargie est faite en Python.
-- Les annonces professionnelles sont incluses ; celles exclues pour mot-clé (épave, moteur HS…) non.
SELECT l.source, l.listing_id, l.price_eur, l.year, l.mileage_km, l.seller_type, l.city
FROM `${project}.${dataset}.listings` AS l
LEFT JOIN `${project}.${dataset}.v_latest_evaluation` AS e USING (source, listing_id)
WHERE l.brand_norm = @brand_norm
  AND l.model_norm = @model_norm
  AND l.fuel = @fuel
  AND l.gearbox = @gearbox
  AND l.last_seen_at >= @since
  AND NOT (l.source = @source AND l.listing_id = @listing_id)
  AND l.price_eur IS NOT NULL AND l.year IS NOT NULL AND l.mileage_km IS NOT NULL
  AND ABS(l.year - @year) <= 2
  AND ABS(l.mileage_km - @mileage_km) <= 40000
  AND IFNULL(e.exclusion_reason, '') != 'mot_cle'
