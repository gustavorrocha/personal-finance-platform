-- Editable two-level spending categories and the rules that assign them.
-- Category and rule changes are append-only events; the latest event wins.
CREATE TABLE IF NOT EXISTS core.spending_categories
(
    category_id UUID,
    parent_id UUID,
    name String,
    archived Bool,
    changed_at DateTime64(6, 'UTC') DEFAULT now64(6),
    event_id UUID DEFAULT generateUUIDv4()
)
ENGINE = MergeTree
ORDER BY (category_id, changed_at, event_id);

-- scope: merchant (merchant fingerprint), mcc (card MCC), provider (Pluggy category code).
-- A zero category_id clears the rule.
CREATE TABLE IF NOT EXISTS core.category_rules
(
    scope LowCardinality(String),
    rule_key String,
    category_id UUID,
    changed_at DateTime64(6, 'UTC') DEFAULT now64(6),
    event_id UUID DEFAULT generateUUIDv4(),
    CONSTRAINT valid_scope CHECK scope IN ('merchant', 'mcc', 'provider')
)
ENGINE = MergeTree
ORDER BY (scope, rule_key, changed_at, event_id);

INSERT INTO core.spending_categories (category_id, parent_id, name, archived, changed_at) VALUES
    ('78bc18fc-69e1-58ac-bece-f4401c5b1d8f', '00000000-0000-0000-0000-000000000000', 'Alimentação', false, '2026-11-19 00:00:00'),
    ('9421890b-b719-52f1-a44a-565b5a6b640b', '78bc18fc-69e1-58ac-bece-f4401c5b1d8f', 'Supermercado', false, '2026-11-19 00:00:00'),
    ('8f0b97a8-f085-5eb2-b322-4477763456e5', '78bc18fc-69e1-58ac-bece-f4401c5b1d8f', 'Restaurantes e bares', false, '2026-11-19 00:00:00'),
    ('88bbd1fa-0af1-5162-b8dd-518624b43005', '78bc18fc-69e1-58ac-bece-f4401c5b1d8f', 'Delivery', false, '2026-11-19 00:00:00'),
    ('7c092d32-2615-5773-bfd5-8d6cc8cd9e16', '00000000-0000-0000-0000-000000000000', 'Transporte', false, '2026-11-19 00:00:00'),
    ('246ea894-d125-5bb5-9927-212aa6ea74c3', '7c092d32-2615-5773-bfd5-8d6cc8cd9e16', 'App e táxi', false, '2026-11-19 00:00:00'),
    ('dd42bf82-3da6-50e8-919c-cc2a158d6c34', '7c092d32-2615-5773-bfd5-8d6cc8cd9e16', 'Transporte público', false, '2026-11-19 00:00:00'),
    ('77505f58-e0b5-50da-9e87-0eb380da68cb', '7c092d32-2615-5773-bfd5-8d6cc8cd9e16', 'Viagens', false, '2026-11-19 00:00:00'),
    ('5a8a9c0e-22eb-5e5d-8d85-8000a4f8d6ee', '00000000-0000-0000-0000-000000000000', 'Moradia', false, '2026-11-19 00:00:00'),
    ('c1d30bf5-8a0e-5dde-97d1-cbd4f2555be7', '5a8a9c0e-22eb-5e5d-8d85-8000a4f8d6ee', 'Aluguel e condomínio', false, '2026-11-19 00:00:00'),
    ('5b3aea76-4c54-528b-92e3-53fa7cc47b37', '5a8a9c0e-22eb-5e5d-8d85-8000a4f8d6ee', 'Energia', false, '2026-11-19 00:00:00'),
    ('a4ccff7e-8009-520d-af08-774012e50db6', '5a8a9c0e-22eb-5e5d-8d85-8000a4f8d6ee', 'Água', false, '2026-11-19 00:00:00'),
    ('53d659d6-5244-5dc0-a033-e7cab53b4a95', '5a8a9c0e-22eb-5e5d-8d85-8000a4f8d6ee', 'Gás', false, '2026-11-19 00:00:00'),
    ('ffbab933-2128-510d-8928-0e23d61b4b91', '5a8a9c0e-22eb-5e5d-8d85-8000a4f8d6ee', 'Internet, TV e telefone', false, '2026-11-19 00:00:00'),
    ('9e2fa5f0-6a13-54bb-8525-4721745a5820', '5a8a9c0e-22eb-5e5d-8d85-8000a4f8d6ee', 'Casa e decoração', false, '2026-11-19 00:00:00'),
    ('b182f0da-450a-538c-8b4e-a4689de09f35', '5a8a9c0e-22eb-5e5d-8d85-8000a4f8d6ee', 'Manutenção e serviços domésticos', false, '2026-11-19 00:00:00'),
    ('11c713ad-a21a-5298-93e1-0aadee0653eb', '00000000-0000-0000-0000-000000000000', 'Saúde e bem-estar', false, '2026-11-19 00:00:00'),
    ('dbb3d8bd-d25c-5fc2-afea-86121df6359c', '11c713ad-a21a-5298-93e1-0aadee0653eb', 'Farmácia', false, '2026-11-19 00:00:00'),
    ('a3359cc5-e739-508e-894d-1767c60b9106', '11c713ad-a21a-5298-93e1-0aadee0653eb', 'Academia e esportes', false, '2026-11-19 00:00:00'),
    ('90a0cef8-f31c-52c2-8379-6983db9050f8', '00000000-0000-0000-0000-000000000000', 'Compras', false, '2026-11-19 00:00:00'),
    ('f1516a8f-6368-51bb-b43d-b174671be27c', '90a0cef8-f31c-52c2-8379-6983db9050f8', 'Roupas e acessórios', false, '2026-11-19 00:00:00'),
    ('9ecaee11-fc46-57dc-bc2a-1e051836bca3', '90a0cef8-f31c-52c2-8379-6983db9050f8', 'Eletrônicos', false, '2026-11-19 00:00:00'),
    ('be4a90c2-9b41-5a34-bc2e-88afa175b854', '90a0cef8-f31c-52c2-8379-6983db9050f8', 'Compras online', false, '2026-11-19 00:00:00'),
    ('c4c42746-10c9-5372-a1c8-4f0bfdd95009', '90a0cef8-f31c-52c2-8379-6983db9050f8', 'Presentes', false, '2026-11-19 00:00:00'),
    ('38b5d6e8-f74a-5908-b6c4-63f0584398ea', '00000000-0000-0000-0000-000000000000', 'Lazer', false, '2026-11-19 00:00:00'),
    ('a898c9bf-404c-5c05-b832-fcaddc87c4b8', '38b5d6e8-f74a-5908-b6c4-63f0584398ea', 'Cinema, shows e eventos', false, '2026-11-19 00:00:00'),
    ('448b0c0b-e1e3-5009-92f2-f0632f86c098', '38b5d6e8-f74a-5908-b6c4-63f0584398ea', 'Hospedagem e passeios', false, '2026-11-19 00:00:00'),
    ('00439952-bb9d-561a-84e1-00b79bf75d35', '38b5d6e8-f74a-5908-b6c4-63f0584398ea', 'Hobbies', false, '2026-11-19 00:00:00'),
    ('6a0d2407-358c-56a3-9076-18286a9eca64', '00000000-0000-0000-0000-000000000000', 'Assinaturas e serviços digitais', false, '2026-11-19 00:00:00'),
    ('1db0ffa6-e62f-5fe0-a875-8aebaae0c18b', '6a0d2407-358c-56a3-9076-18286a9eca64', 'Streaming', false, '2026-11-19 00:00:00'),
    ('72046338-ec81-5c64-a5ba-fca463037bce', '6a0d2407-358c-56a3-9076-18286a9eca64', 'Apps e software', false, '2026-11-19 00:00:00'),
    ('6ae24738-cc02-57bc-adc9-22922d4efce4', '6a0d2407-358c-56a3-9076-18286a9eca64', 'Outros serviços digitais', false, '2026-11-19 00:00:00'),
    ('a42dfb1e-b829-5360-b265-53a49c8f4669', '00000000-0000-0000-0000-000000000000', 'Serviços pessoais', false, '2026-11-19 00:00:00'),
    ('a08df5c8-3121-5f2f-a800-8231485b3a30', 'a42dfb1e-b829-5360-b265-53a49c8f4669', 'Lavanderia', false, '2026-11-19 00:00:00'),
    ('e9132ec8-6a50-53ac-9bfa-00aac4e0a474', 'a42dfb1e-b829-5360-b265-53a49c8f4669', 'Cabeleireiro e estética', false, '2026-11-19 00:00:00'),
    ('32516c49-1a8d-5bac-bec4-79159871195a', '00000000-0000-0000-0000-000000000000', 'Outros', false, '2026-11-19 00:00:00');

INSERT INTO core.category_rules (scope, rule_key, category_id, changed_at) VALUES
    ('provider', '10000000', '9421890b-b719-52f1-a44a-565b5a6b640b', '2026-11-19 00:00:00'),
    ('provider', '11000000', '78bc18fc-69e1-58ac-bece-f4401c5b1d8f', '2026-11-19 00:00:00'),
    ('provider', '11010000', '8f0b97a8-f085-5eb2-b322-4477763456e5', '2026-11-19 00:00:00'),
    ('provider', '11020000', '88bbd1fa-0af1-5162-b8dd-518624b43005', '2026-11-19 00:00:00'),
    ('provider', '19000000', '7c092d32-2615-5773-bfd5-8d6cc8cd9e16', '2026-11-19 00:00:00'),
    ('provider', '19010000', '246ea894-d125-5bb5-9927-212aa6ea74c3', '2026-11-19 00:00:00'),
    ('provider', '19020000', 'dd42bf82-3da6-50e8-919c-cc2a158d6c34', '2026-11-19 00:00:00'),
    ('provider', '19030000', '7c092d32-2615-5773-bfd5-8d6cc8cd9e16', '2026-11-19 00:00:00'),
    ('provider', '12000000', '77505f58-e0b5-50da-9e87-0eb380da68cb', '2026-11-19 00:00:00'),
    ('provider', '12010000', '77505f58-e0b5-50da-9e87-0eb380da68cb', '2026-11-19 00:00:00'),
    ('provider', '17000000', '5a8a9c0e-22eb-5e5d-8d85-8000a4f8d6ee', '2026-11-19 00:00:00'),
    ('provider', '17020002', '5b3aea76-4c54-528b-92e3-53fa7cc47b37', '2026-11-19 00:00:00'),
    ('provider', '17020003', '53d659d6-5244-5dc0-a033-e7cab53b4a95', '2026-11-19 00:00:00'),
    ('provider', '17030000', '9e2fa5f0-6a13-54bb-8525-4721745a5820', '2026-11-19 00:00:00'),
    ('provider', '07010000', 'ffbab933-2128-510d-8928-0e23d61b4b91', '2026-11-19 00:00:00'),
    ('provider', '18000000', '11c713ad-a21a-5298-93e1-0aadee0653eb', '2026-11-19 00:00:00'),
    ('provider', '18020000', 'dbb3d8bd-d25c-5fc2-afea-86121df6359c', '2026-11-19 00:00:00'),
    ('provider', '07030001', 'a3359cc5-e739-508e-894d-1767c60b9106', '2026-11-19 00:00:00'),
    ('provider', '07030002', 'a3359cc5-e739-508e-894d-1767c60b9106', '2026-11-19 00:00:00'),
    ('provider', '07000000', 'a42dfb1e-b829-5360-b265-53a49c8f4669', '2026-11-19 00:00:00'),
    ('provider', '07040000', 'a898c9bf-404c-5c05-b832-fcaddc87c4b8', '2026-11-19 00:00:00'),
    ('provider', '07040003', 'a898c9bf-404c-5c05-b832-fcaddc87c4b8', '2026-11-19 00:00:00'),
    ('provider', '08070000', '00439952-bb9d-561a-84e1-00b79bf75d35', '2026-11-19 00:00:00'),
    ('provider', '14010000', '38b5d6e8-f74a-5908-b6c4-63f0584398ea', '2026-11-19 00:00:00'),
    ('provider', '08000000', '90a0cef8-f31c-52c2-8379-6983db9050f8', '2026-11-19 00:00:00'),
    ('provider', '08010000', 'be4a90c2-9b41-5a34-bc2e-88afa175b854', '2026-11-19 00:00:00'),
    ('provider', '08020000', '9ecaee11-fc46-57dc-bc2a-1e051836bca3', '2026-11-19 00:00:00'),
    ('provider', '08030000', '90a0cef8-f31c-52c2-8379-6983db9050f8', '2026-11-19 00:00:00'),
    ('provider', '08040000', 'f1516a8f-6368-51bb-b43d-b174671be27c', '2026-11-19 00:00:00'),
    ('provider', '08050000', '90a0cef8-f31c-52c2-8379-6983db9050f8', '2026-11-19 00:00:00'),
    ('provider', '08060000', '90a0cef8-f31c-52c2-8379-6983db9050f8', '2026-11-19 00:00:00'),
    ('provider', '08080000', '90a0cef8-f31c-52c2-8379-6983db9050f8', '2026-11-19 00:00:00'),
    ('provider', '09000000', '6a0d2407-358c-56a3-9076-18286a9eca64', '2026-11-19 00:00:00'),
    ('provider', '02010000', '32516c49-1a8d-5bac-bec4-79159871195a', '2026-11-19 00:00:00'),
    ('provider', '02020000', '32516c49-1a8d-5bac-bec4-79159871195a', '2026-11-19 00:00:00'),
    ('provider', '15030000', '32516c49-1a8d-5bac-bec4-79159871195a', '2026-11-19 00:00:00'),
    ('provider', '99999999', '32516c49-1a8d-5bac-bec4-79159871195a', '2026-11-19 00:00:00'),
    ('mcc', '5411', '9421890b-b719-52f1-a44a-565b5a6b640b', '2026-11-19 00:00:00'),
    ('mcc', '5422', '9421890b-b719-52f1-a44a-565b5a6b640b', '2026-11-19 00:00:00'),
    ('mcc', '5441', '9421890b-b719-52f1-a44a-565b5a6b640b', '2026-11-19 00:00:00'),
    ('mcc', '5451', '9421890b-b719-52f1-a44a-565b5a6b640b', '2026-11-19 00:00:00'),
    ('mcc', '5462', '9421890b-b719-52f1-a44a-565b5a6b640b', '2026-11-19 00:00:00'),
    ('mcc', '5499', '9421890b-b719-52f1-a44a-565b5a6b640b', '2026-11-19 00:00:00'),
    ('mcc', '5812', '8f0b97a8-f085-5eb2-b322-4477763456e5', '2026-11-19 00:00:00'),
    ('mcc', '5813', '8f0b97a8-f085-5eb2-b322-4477763456e5', '2026-11-19 00:00:00'),
    ('mcc', '5814', '8f0b97a8-f085-5eb2-b322-4477763456e5', '2026-11-19 00:00:00'),
    ('mcc', '4121', '246ea894-d125-5bb5-9927-212aa6ea74c3', '2026-11-19 00:00:00'),
    ('mcc', '4111', 'dd42bf82-3da6-50e8-919c-cc2a158d6c34', '2026-11-19 00:00:00'),
    ('mcc', '4131', 'dd42bf82-3da6-50e8-919c-cc2a158d6c34', '2026-11-19 00:00:00'),
    ('mcc', '4511', '77505f58-e0b5-50da-9e87-0eb380da68cb', '2026-11-19 00:00:00'),
    ('mcc', '4722', '77505f58-e0b5-50da-9e87-0eb380da68cb', '2026-11-19 00:00:00'),
    ('mcc', '7011', '448b0c0b-e1e3-5009-92f2-f0632f86c098', '2026-11-19 00:00:00'),
    ('mcc', '5912', 'dbb3d8bd-d25c-5fc2-afea-86121df6359c', '2026-11-19 00:00:00'),
    ('mcc', '7997', 'a3359cc5-e739-508e-894d-1767c60b9106', '2026-11-19 00:00:00'),
    ('mcc', '4899', '1db0ffa6-e62f-5fe0-a875-8aebaae0c18b', '2026-11-19 00:00:00'),
    ('mcc', '5734', '72046338-ec81-5c64-a5ba-fca463037bce', '2026-11-19 00:00:00'),
    ('mcc', '5817', '72046338-ec81-5c64-a5ba-fca463037bce', '2026-11-19 00:00:00'),
    ('mcc', '5818', '72046338-ec81-5c64-a5ba-fca463037bce', '2026-11-19 00:00:00'),
    ('mcc', '7372', '72046338-ec81-5c64-a5ba-fca463037bce', '2026-11-19 00:00:00'),
    ('mcc', '4814', 'ffbab933-2128-510d-8928-0e23d61b4b91', '2026-11-19 00:00:00'),
    ('mcc', '4900', '5b3aea76-4c54-528b-92e3-53fa7cc47b37', '2026-11-19 00:00:00'),
    ('mcc', '5200', '9e2fa5f0-6a13-54bb-8525-4721745a5820', '2026-11-19 00:00:00'),
    ('mcc', '5251', '9e2fa5f0-6a13-54bb-8525-4721745a5820', '2026-11-19 00:00:00'),
    ('mcc', '5712', '9e2fa5f0-6a13-54bb-8525-4721745a5820', '2026-11-19 00:00:00'),
    ('mcc', '5719', '9e2fa5f0-6a13-54bb-8525-4721745a5820', '2026-11-19 00:00:00'),
    ('mcc', '5611', 'f1516a8f-6368-51bb-b43d-b174671be27c', '2026-11-19 00:00:00'),
    ('mcc', '5621', 'f1516a8f-6368-51bb-b43d-b174671be27c', '2026-11-19 00:00:00'),
    ('mcc', '5641', 'f1516a8f-6368-51bb-b43d-b174671be27c', '2026-11-19 00:00:00'),
    ('mcc', '5651', 'f1516a8f-6368-51bb-b43d-b174671be27c', '2026-11-19 00:00:00'),
    ('mcc', '5661', 'f1516a8f-6368-51bb-b43d-b174671be27c', '2026-11-19 00:00:00'),
    ('mcc', '5691', 'f1516a8f-6368-51bb-b43d-b174671be27c', '2026-11-19 00:00:00'),
    ('mcc', '5699', 'f1516a8f-6368-51bb-b43d-b174671be27c', '2026-11-19 00:00:00'),
    ('mcc', '5722', '9ecaee11-fc46-57dc-bc2a-1e051836bca3', '2026-11-19 00:00:00'),
    ('mcc', '5732', '9ecaee11-fc46-57dc-bc2a-1e051836bca3', '2026-11-19 00:00:00'),
    ('mcc', '5311', '90a0cef8-f31c-52c2-8379-6983db9050f8', '2026-11-19 00:00:00'),
    ('mcc', '5331', '90a0cef8-f31c-52c2-8379-6983db9050f8', '2026-11-19 00:00:00'),
    ('mcc', '5399', '90a0cef8-f31c-52c2-8379-6983db9050f8', '2026-11-19 00:00:00'),
    ('mcc', '5942', '90a0cef8-f31c-52c2-8379-6983db9050f8', '2026-11-19 00:00:00'),
    ('mcc', '5943', '90a0cef8-f31c-52c2-8379-6983db9050f8', '2026-11-19 00:00:00'),
    ('mcc', '5945', '90a0cef8-f31c-52c2-8379-6983db9050f8', '2026-11-19 00:00:00'),
    ('mcc', '7832', 'a898c9bf-404c-5c05-b832-fcaddc87c4b8', '2026-11-19 00:00:00'),
    ('mcc', '7922', 'a898c9bf-404c-5c05-b832-fcaddc87c4b8', '2026-11-19 00:00:00'),
    ('mcc', '7210', 'a08df5c8-3121-5f2f-a800-8231485b3a30', '2026-11-19 00:00:00'),
    ('mcc', '7211', 'a08df5c8-3121-5f2f-a800-8231485b3a30', '2026-11-19 00:00:00'),
    ('mcc', '7216', 'a08df5c8-3121-5f2f-a800-8231485b3a30', '2026-11-19 00:00:00'),
    ('mcc', '7230', 'e9132ec8-6a50-53ac-9bfa-00aac4e0a474', '2026-11-19 00:00:00'),
    ('mcc', '7298', 'e9132ec8-6a50-53ac-9bfa-00aac4e0a474', '2026-11-19 00:00:00');

INSERT INTO core.category_rules (scope, rule_key, category_id, changed_at)
SELECT 'mcc', toString(number), toUUID('77505f58-e0b5-50da-9e87-0eb380da68cb'), toDateTime64('2026-11-19 00:00:00', 6, 'UTC') FROM numbers(3000, 300)
UNION ALL
SELECT 'mcc', toString(number), toUUID('448b0c0b-e1e3-5009-92f2-f0632f86c098'), toDateTime64('2026-11-19 00:00:00', 6, 'UTC') FROM numbers(3501, 299);

-- Active categories: not archived and, for subcategories, under an active category.
CREATE VIEW IF NOT EXISTS analytics.spending_categories
DEFINER = CURRENT_USER SQL SECURITY DEFINER AS
WITH latest AS
(
    SELECT category_id,
           argMax(parent_id, (changed_at, event_id)) AS parent_id,
           argMax(name, (changed_at, event_id)) AS name,
           argMax(archived, (changed_at, event_id)) AS archived
    FROM core.spending_categories
    GROUP BY category_id
)
SELECT category_id, parent_id, name
FROM latest
WHERE NOT archived
  AND (parent_id = toUUID('00000000-0000-0000-0000-000000000000')
       OR parent_id IN (SELECT category_id FROM latest
                        WHERE NOT archived AND parent_id = toUUID('00000000-0000-0000-0000-000000000000')));

CREATE VIEW IF NOT EXISTS core.category_rule_current
DEFINER = CURRENT_USER SQL SECURITY DEFINER AS
SELECT r.scope AS scope,
       r.rule_key AS rule_key,
       toString(c.category_id) AS category_id,
       if(c.parent_id = toUUID('00000000-0000-0000-0000-000000000000'), c.name, p.name) AS category,
       if(c.parent_id = toUUID('00000000-0000-0000-0000-000000000000'), '', c.name) AS subcategory
FROM
(
    SELECT scope, rule_key, argMax(category_id, (changed_at, event_id)) AS category_id
    FROM core.category_rules
    GROUP BY scope, rule_key
) AS r
INNER JOIN analytics.spending_categories AS c ON r.category_id = c.category_id
LEFT JOIN analytics.spending_categories AS p ON c.parent_id = p.category_id;

-- In-memory rule lookup for the spending views. The API reloads it after each change.
CREATE DICTIONARY IF NOT EXISTS core.category_rule_dict
(
    scope String,
    rule_key String,
    category_id String,
    category String,
    subcategory String
)
PRIMARY KEY scope, rule_key
SOURCE(CLICKHOUSE(QUERY 'SELECT scope, rule_key, category_id, category, subcategory FROM core.category_rule_current'))
LIFETIME(MIN 30 MAX 60)
LAYOUT(COMPLEX_KEY_HASHED());

CREATE OR REPLACE VIEW analytics.spending_dashboard
DEFINER = CURRENT_USER SQL SECURITY DEFINER AS
SELECT t.item_key AS item_key,
       t.entity_key AS transaction_key,
       t.economic_date AS economic_date,
       t.currency AS currency,
       if(t.spending_kind = 'refund', -abs(t.amount), abs(t.amount)) AS net_amount,
       t.merchant_label AS merchant_label,
       t.spending_operation AS operation,
       t.bank_description AS description,
       t.bank_category AS bank_category,
       t.transaction_time AS transaction_time,
       t.original_purchase_date AS original_purchase_date,
       t.installment_number AS installment_number,
       t.total_installments AS total_installments,
       t.installment_total_amount AS installment_total_amount,
       t.merchant_key AS merchant_key,
       t.category_id AS provider_category_id,
       t.mcc AS mcc,
       if(t.merchant_cnpj != '', t.merchant_cnpj, t.counterparty_cnpj) AS cnpj,
       t.merchant_cnae AS cnae,
       if(t.merchant_business_name != '', t.merchant_business_name, t.counterparty_name) AS business_name,
       t.merchant_category AS merchant_category,
       if(c.is_card, 'card', 'bank') AS source,
       dictGetOrDefault('core.category_rule_dict', ('category_id', 'category', 'subcategory'), ('merchant', t.merchant_key), ('', '', '')) AS merchant_rule,
       dictGetOrDefault('core.category_rule_dict', ('category_id', 'category', 'subcategory'), ('provider', t.category_id), ('', '', '')) AS provider_rule,
       dictGetOrDefault('core.category_rule_dict', ('category_id', 'category', 'subcategory'), ('mcc', ifNull(toString(t.mcc), '')), ('', '', '')) AS mcc_rule,
       dictGetOrDefault('core.category_rule_dict', ('category_id', 'category', 'subcategory'), ('provider', concat(substring(t.category_id, 1, 2), '000000')), ('', '', '')) AS group_rule,
       multiIf(
           merchant_rule.1 != '', ('merchant', merchant_rule),
           provider_rule.1 != '' AND NOT endsWith(t.category_id, '000000'),
               ('provider', provider_rule),
           mcc_rule.1 != '', ('mcc', mcc_rule),
           provider_rule.1 != '', ('provider', provider_rule),
           group_rule.1 != '', ('provider', group_rule),
           ('', ('', '', ''))) AS chosen_category,
       chosen_category.2.2 AS category,
       chosen_category.2.3 AS subcategory,
       chosen_category.2.1 AS category_id,
       chosen_category.1 AS category_rule,
       ifNull(nullIf(d.decision, 'reset'), '') AS decision,
       multiIf(t.spending_kind = 'refund', true,
               d.decision = 'include', true, d.decision = 'exclude', false,
               t.spending_kind = 'purchase') AS included,
       t.spending_kind != 'refund'
           AND (t.spending_kind = 'review' OR d.decision IN ('include', 'exclude')) AS reviewable
FROM
(
    SELECT *
    FROM core.provider_versions FINAL
    WHERE resource = 'transactions'
      AND run_id IN (SELECT run_id FROM metadata.ingestion_publications)
    ORDER BY observed_at DESC, run_id DESC, row_order DESC
    LIMIT 1 BY item_key, entity_key
) AS t
LEFT JOIN
(
    SELECT DISTINCT item_key, entity_key, true AS is_card FROM core.credit_card_current
) AS c ON t.item_key = c.item_key AND t.scope_id = c.entity_key
LEFT JOIN
(
    SELECT item_key, transaction_key, argMax(decision, (decided_at, event_id)) AS decision
    FROM core.spending_reviews
    GROUP BY item_key, transaction_key
) AS d ON t.item_key = d.item_key AND t.entity_key = d.transaction_key
WHERE NOT t.deleted AND t.status = 'POSTED' AND t.spending_kind IN ('purchase', 'refund', 'review')
    AND t.economic_date IS NOT NULL AND t.currency IS NOT NULL AND t.amount IS NOT NULL;


CREATE OR REPLACE VIEW analytics.pending_card_spending
DEFINER = CURRENT_USER SQL SECURITY DEFINER AS
SELECT t.item_key AS item_key,
       t.economic_date AS economic_date,
       t.currency AS currency,
       t.bank_description AS description,
       t.bank_category AS bank_category,
       t.transaction_time AS transaction_time,
       t.original_purchase_date AS original_purchase_date,
       t.installment_number AS installment_number,
       t.total_installments AS total_installments,
       t.installment_total_amount AS installment_total_amount,
       t.entity_key AS transaction_key,
       t.merchant_label AS merchant_label,
       t.mcc AS mcc,
       if(t.merchant_cnpj != '', t.merchant_cnpj, t.counterparty_cnpj) AS cnpj,
       t.merchant_cnae AS cnae,
       if(t.merchant_business_name != '', t.merchant_business_name, t.counterparty_name) AS business_name,
       t.merchant_category AS merchant_category,
       dictGetOrDefault('core.category_rule_dict', ('category_id', 'category', 'subcategory'), ('merchant', t.merchant_key), ('', '', '')) AS merchant_rule,
       dictGetOrDefault('core.category_rule_dict', ('category_id', 'category', 'subcategory'), ('provider', t.category_id), ('', '', '')) AS provider_rule,
       dictGetOrDefault('core.category_rule_dict', ('category_id', 'category', 'subcategory'), ('mcc', ifNull(toString(t.mcc), '')), ('', '', '')) AS mcc_rule,
       dictGetOrDefault('core.category_rule_dict', ('category_id', 'category', 'subcategory'), ('provider', concat(substring(t.category_id, 1, 2), '000000')), ('', '', '')) AS group_rule,
       multiIf(
           merchant_rule.1 != '', ('merchant', merchant_rule),
           provider_rule.1 != '' AND NOT endsWith(t.category_id, '000000'),
               ('provider', provider_rule),
           mcc_rule.1 != '', ('mcc', mcc_rule),
           provider_rule.1 != '', ('provider', provider_rule),
           group_rule.1 != '', ('provider', group_rule),
           ('', ('', '', ''))) AS chosen_category,
       chosen_category.2.2 AS category,
       chosen_category.2.3 AS subcategory,
       chosen_category.2.1 AS category_id,
       chosen_category.1 AS category_rule,
       t.amount AS amount
FROM
(
    SELECT item_key, entity_key, scope_id, economic_date, currency, amount,
           type, status, spending_kind, deleted, merchant_label, bank_description, bank_category,
           transaction_time, original_purchase_date, installment_number, total_installments,
           installment_total_amount, spending_category, mcc, merchant_cnpj, counterparty_cnpj,
           merchant_cnae, merchant_business_name, counterparty_name, merchant_category,
           merchant_key, category_id
    FROM core.provider_versions FINAL
    WHERE resource = 'transactions'
      AND run_id IN (SELECT run_id FROM metadata.ingestion_publications)
    ORDER BY observed_at DESC, run_id DESC, row_order DESC
    LIMIT 1 BY item_key, entity_key
) AS t
INNER JOIN core.credit_card_current AS a
    ON t.item_key = a.item_key AND t.scope_id = a.entity_key
WHERE NOT t.deleted AND t.status = 'PENDING' AND t.type = 'DEBIT'
    AND t.spending_kind = 'purchase'
    AND t.economic_date IS NOT NULL AND t.currency IS NOT NULL AND t.amount > 0;
