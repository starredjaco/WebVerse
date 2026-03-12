-- Poppet Lab: Per-service database architecture

SET NAMES utf8mb4;

-- ===== DATABASES =====
CREATE DATABASE IF NOT EXISTS app_db;
CREATE DATABASE IF NOT EXISTS shop_db;
CREATE DATABASE IF NOT EXISTS crm_db;
CREATE DATABASE IF NOT EXISTS payroll_db;
CREATE DATABASE IF NOT EXISTS dispatch_db;

-- ===== SERVICE ACCOUNTS =====
CREATE USER IF NOT EXISTS 'app_svc'@'%' IDENTIFIED WITH mysql_native_password BY 'AppSvc#2024!';
CREATE USER IF NOT EXISTS 'shop_svc'@'%' IDENTIFIED WITH mysql_native_password BY 'ShopSvc#2024!';
CREATE USER IF NOT EXISTS 'connect_svc'@'%' IDENTIFIED WITH mysql_native_password BY 'ConnSvc#2024!';
CREATE USER IF NOT EXISTS 'crm_svc'@'%' IDENTIFIED WITH mysql_native_password BY 'CrmSvc#2024!';
CREATE USER IF NOT EXISTS 'payroll_svc'@'%' IDENTIFIED WITH mysql_native_password BY 'PaySvc#2024!';
CREATE USER IF NOT EXISTS 'dispatch_svc'@'%' IDENTIFIED WITH mysql_native_password BY 'DspSvc#2024!';

-- ===== GRANTS =====
GRANT ALL PRIVILEGES ON app_db.* TO 'app_svc'@'%';

GRANT ALL PRIVILEGES ON shop_db.* TO 'shop_svc'@'%';
GRANT SELECT ON dispatch_db.* TO 'shop_svc'@'%';

GRANT SELECT ON shop_db.* TO 'connect_svc'@'%';

GRANT ALL PRIVILEGES ON crm_db.* TO 'crm_svc'@'%';

GRANT ALL PRIVILEGES ON payroll_db.* TO 'payroll_svc'@'%';
GRANT SELECT ON crm_db.* TO 'payroll_svc'@'%';

GRANT ALL PRIVILEGES ON dispatch_db.* TO 'dispatch_svc'@'%';
GRANT SELECT ON shop_db.* TO 'dispatch_svc'@'%';
-- Over-scoped: dispatch has no business need for CRM data (ticket INFRA-2847)
GRANT SELECT ON crm_db.* TO 'dispatch_svc'@'%';

FLUSH PRIVILEGES;

-- ===== app_db =====
USE app_db;
CREATE TABLE app_users (id INT PRIMARY KEY AUTO_INCREMENT, username VARCHAR(50) UNIQUE NOT NULL, password VARCHAR(255) NOT NULL, full_name VARCHAR(100), role VARCHAR(20) DEFAULT 'user', bio TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE toy_designs (id INT PRIMARY KEY AUTO_INCREMENT, user_id INT, name VARCHAR(100), description TEXT, category VARCHAR(30), materials_used VARCHAR(200), age_range VARCHAR(20), image_data LONGTEXT, image_slug VARCHAR(50), status VARCHAR(20) DEFAULT 'draft', reviewer_notes TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE materials (id INT PRIMARY KEY AUTO_INCREMENT, name VARCHAR(100), category VARCHAR(30), supplier VARCHAR(100), unit VARCHAR(20), stock_qty INT DEFAULT 0, min_qty INT DEFAULT 10, notes TEXT);
CREATE TABLE production_queue (id INT PRIMARY KEY AUTO_INCREMENT, design_id INT, assigned_to INT, priority VARCHAR(10) DEFAULT 'normal', status VARCHAR(20) DEFAULT 'queued', qty_ordered INT DEFAULT 1, due_date DATE, notes TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE contact_messages (id INT PRIMARY KEY AUTO_INCREMENT, name VARCHAR(100), email VARCHAR(100), subject VARCHAR(200), message TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);

INSERT INTO app_users (username, password, full_name, role, bio) VALUES ('toybot', 'FactoryLine!2024', 'Studio Automation', 'designer', 'Automated design pipeline account for batch processing and template generation.');
INSERT INTO app_users (username, password, full_name, role, bio) VALUES ('a.patel', 'DesignAisha1!', 'Aisha Patel', 'designer', 'Lead concept artist specializing in figurines and miniatures. 8 years in toy design.');
INSERT INTO app_users (username, password, full_name, role, bio) VALUES ('c.rivera', 'DevCarlos1!', 'Carlos Rivera', 'user', 'Junior designer focusing on educational kits and packaging.');
INSERT INTO app_users (username, password, full_name, role, bio) VALUES ('m.chen', 'StudioMei2024!', 'Mei Chen', 'designer', 'Plush and textile specialist. Former Pattern Maker at Jellycat.');

INSERT INTO toy_designs (user_id, name, description, category, materials_used, age_range, status, created_at) VALUES (2, 'Midnight Owl Figurine', 'Hand-carved walnut owl with inlaid glass eyes and felt wing details. Each piece is unique with natural wood grain variations.', 'figurines', 'walnut, glass beads, felt, beeswax', '3+', 'approved', '2024-11-02 09:15:00');
INSERT INTO toy_designs (user_id, name, description, category, materials_used, age_range, status, created_at) VALUES (2, 'Coral Reef Bath Friends', 'Waterproof natural rubber sea creatures with non-toxic paint. Set of 5 includes starfish, seahorse, turtle, octopus, and clownfish.', 'bath', 'natural rubber, non-toxic paint', '1+', 'review', '2024-11-18 14:30:00');
INSERT INTO toy_designs (user_id, name, description, category, materials_used, age_range, status, created_at) VALUES (1, 'Modular Treehouse Kit', 'Snap-together birch treehouse with 4 rooms and rope ladder. No glue needed. Includes 2 wooden figurines.', 'construction', 'birch plywood, cotton rope, beeswax', '4+', 'draft', '2024-12-01 10:00:00');
INSERT INTO toy_designs (user_id, name, description, category, materials_used, age_range, status, created_at) VALUES (2, 'Autumn Mushroom Garden', 'Painted wooden mushrooms in a moss-lined display tray. Decorative collectible set of 8.', 'figurines', 'maple, acrylic paint, preserved moss', '6+', 'approved', '2024-10-15 11:20:00');
INSERT INTO toy_designs (user_id, name, description, category, materials_used, age_range, status, created_at) VALUES (4, 'Sleepy Fox Plush', 'Hand-stitched wool felt fox with embroidered eyes and a removable knit scarf. 12 inches.', 'plush', 'merino wool felt, cotton fill, yarn', '2+', 'approved', '2024-11-25 16:45:00');
INSERT INTO toy_designs (user_id, name, description, category, materials_used, age_range, status, created_at) VALUES (3, 'Rainbow Peg Board', 'Birch pegboard with 36 colored maple pegs in a canvas drawstring bag. Color matching and pattern play.', 'educational', 'birch, maple, non-toxic dye, canvas', '2+', 'review', '2024-12-03 09:00:00');
INSERT INTO toy_designs (user_id, name, description, category, materials_used, age_range, status, created_at) VALUES (4, 'Cloud Lamb Family', 'Set of 3 organic cotton lambs (mama, papa, baby) with lavender sachet inserts.', 'plush', 'organic cotton, cotton fill, dried lavender', '0+', 'approved', '2024-10-28 13:00:00');
INSERT INTO toy_designs (user_id, name, description, category, materials_used, age_range, status, created_at) VALUES (2, 'Woodland Stacking Rings', 'Graduated maple rings painted as forest animals. Stack on a walnut post. Set of 6.', 'educational', 'maple, walnut, non-toxic paint', '1+', 'approved', '2024-09-20 10:30:00');
INSERT INTO toy_designs (user_id, name, description, category, materials_used, age_range, status, created_at) VALUES (1, 'Constellation Lantern', 'Punched tin lantern with LED tea light. Projects star patterns. Comes with mythology booklet.', 'creative', 'tin, LED, paper', '6+', 'draft', '2024-12-04 15:00:00');
INSERT INTO toy_designs (user_id, name, description, category, materials_used, age_range, status, created_at) VALUES (3, 'Caterpillar Counting Beads', 'Wooden caterpillar with 10 sliding beads for early math. Body segments snap apart for transport.', 'educational', 'beech, non-toxic paint, elastic cord', '2+', 'review', '2024-11-30 08:45:00');


-- Image slugs
UPDATE toy_designs SET image_slug='midnight-owl' WHERE id=1;
UPDATE toy_designs SET image_slug='coral-reef' WHERE id=2;
UPDATE toy_designs SET image_slug='treehouse' WHERE id=3;
UPDATE toy_designs SET image_slug='mushroom-garden' WHERE id=4;
UPDATE toy_designs SET image_slug='sleepy-fox' WHERE id=5;
UPDATE toy_designs SET image_slug='rainbow-pegboard' WHERE id=6;
UPDATE toy_designs SET image_slug='cloud-lamb' WHERE id=7;
UPDATE toy_designs SET image_slug='stacking-rings' WHERE id=8;
UPDATE toy_designs SET image_slug='constellation-lantern' WHERE id=9;
UPDATE toy_designs SET image_slug='caterpillar-beads' WHERE id=10;

INSERT INTO materials (name, category, supplier, unit, stock_qty, min_qty, notes) VALUES ('Walnut Blanks (4x4x6)', 'wood', 'Appalachian Hardwoods Co.', 'piece', 120, 20, 'Grade A, kiln-dried. Lead time 2 weeks.');
INSERT INTO materials (name, category, supplier, unit, stock_qty, min_qty, notes) VALUES ('Birch Plywood 1/4in', 'wood', 'Appalachian Hardwoods Co.', 'sheet', 45, 10, 'Baltic birch, laser-safe grade.');
INSERT INTO materials (name, category, supplier, unit, stock_qty, min_qty, notes) VALUES ('Maple Dowels 3/8in', 'wood', 'Appalachian Hardwoods Co.', 'bundle', 30, 8, '36in length, sanded. Bundle of 25.');
INSERT INTO materials (name, category, supplier, unit, stock_qty, min_qty, notes) VALUES ('Merino Wool Felt (sheet)', 'textile', 'Benzie Design', 'sheet', 200, 40, '9x12in sheets, assorted colors.');
INSERT INTO materials (name, category, supplier, unit, stock_qty, min_qty, notes) VALUES ('Organic Cotton Fill', 'textile', 'Mountain Fiber Supply', 'lb', 35, 10, 'GOTS certified. For plush stuffing.');
INSERT INTO materials (name, category, supplier, unit, stock_qty, min_qty, notes) VALUES ('Non-Toxic Acrylic Paint Set', 'finish', 'Eco-Kids', 'set', 18, 5, '12-color set. ASTM D-4236 certified.');
INSERT INTO materials (name, category, supplier, unit, stock_qty, min_qty, notes) VALUES ('Beeswax Polish', 'finish', 'Heritage Natural Finishes', 'tin', 24, 6, '8oz tin. Food-safe for wooden toys.');
INSERT INTO materials (name, category, supplier, unit, stock_qty, min_qty, notes) VALUES ('Glass Eyes 8mm', 'hardware', 'Teddy Bear Supplies', 'pair', 85, 20, 'Safety-backed for plush. Black and brown.');
INSERT INTO materials (name, category, supplier, unit, stock_qty, min_qty, notes) VALUES ('Natural Rubber Block', 'specialty', 'Pure Rubber Co.', 'block', 15, 5, 'For bath toys. FDA food-grade.');
INSERT INTO materials (name, category, supplier, unit, stock_qty, min_qty, notes) VALUES ('Cotton Rope 4mm', 'textile', 'Mountain Fiber Supply', 'spool', 12, 3, '100ft spool. Unbleached. For pull toys and kits.');

INSERT INTO production_queue (design_id, assigned_to, priority, status, qty_ordered, due_date, notes) VALUES (1, 2, 'high', 'in_progress', 24, '2024-12-20', 'Holiday rush order for Asheville market booth.');
INSERT INTO production_queue (design_id, assigned_to, priority, status, qty_ordered, due_date, notes) VALUES (5, 4, 'normal', 'in_progress', 15, '2024-12-18', 'Wholesale restock for Blue Ridge General.');
INSERT INTO production_queue (design_id, assigned_to, priority, status, qty_ordered, due_date, notes) VALUES (7, 4, 'high', 'queued', 30, '2024-12-22', 'Gift set bundles for holiday pop-up.');
INSERT INTO production_queue (design_id, assigned_to, priority, status, qty_ordered, due_date, notes) VALUES (8, 2, 'normal', 'queued', 20, '2025-01-05', 'January restock.');
INSERT INTO production_queue (design_id, assigned_to, priority, status, qty_ordered, due_date, notes) VALUES (4, 2, 'low', 'completed', 12, '2024-11-30', 'Collector series for Maker Market.');

INSERT INTO contact_messages (name, email, subject, message, created_at) VALUES ('Rebecca Torres', 'rtorres@kidstuff.com', 'Wholesale inquiry', 'Hi, I run a small toy shop in Durham and would love to carry your wooden figurines. What are your wholesale terms?', '2024-12-02 10:15:00');
INSERT INTO contact_messages (name, email, subject, message, created_at) VALUES ('James Liu', 'jliu@parentmag.com', 'Feature article request', 'We are writing a piece on independent toy makers in the Southeast. Would anyone from your team be available for an interview?', '2024-12-04 14:30:00');

-- ===== shop_db =====
USE shop_db;
CREATE TABLE shop_users (id INT PRIMARY KEY AUTO_INCREMENT, username VARCHAR(50) UNIQUE NOT NULL, password VARCHAR(255) NOT NULL, email VARCHAR(100), role VARCHAR(20) DEFAULT 'customer', reset_code VARCHAR(4) DEFAULT NULL, reset_code_expiry DATETIME DEFAULT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE products (id INT PRIMARY KEY AUTO_INCREMENT, name VARCHAR(100) NOT NULL, description TEXT, price DECIMAL(10,2), category VARCHAR(50), stock INT DEFAULT 0, sku VARCHAR(20), created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE orders (id INT PRIMARY KEY AUTO_INCREMENT, user_id INT, product_id INT, quantity INT DEFAULT 1, total DECIMAL(10,2), status VARCHAR(20) DEFAULT 'pending', shipping_address TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);

INSERT INTO shop_users (username, password, email, role) VALUES ('helpdesk', '284fff3bd254b48cca05a8bfc4fad69e05cad0d086513a034a66a118829e6fa4', 'helpdesk@poppet.local', 'helpdesk');
INSERT INTO shop_users (username, password, email, role) VALUES ('warehouse_mgr', '915dfa985b72d57276c8dae432535c693865f4bbc69d665330cd54bb17438eff', 'warehouse@poppet.local', 'staff');
INSERT INTO shop_users (username, password, email, role) VALUES ('sarah.chen', 'c13ff79daa5f61863a9656603affc83428d2a2117f4345c744825abd993996a0', 'sarah.chen@gmail.com', 'customer');
INSERT INTO shop_users (username, password, email, role) VALUES ('mike.ross', 'e5191ab30c939612d9a46f4ce46aff7d9d8d0fea5227c03af2caf91d0bdfd4a7', 'mike.ross@gmail.com', 'customer');
INSERT INTO shop_users (username, password, email, role) VALUES ('linda.wu', '3630fef1e79b6f7429aeea002304125ad3f3b0497c60fd2348d6d1729ffc5bb5', 'linda.wu@gmail.com', 'customer');
INSERT INTO shop_users (username, password, email, role) VALUES ('tom.jones', '0ba74f14a9649b9a91505dd64af9922b21476990e6b5756d1ea8ed1b4d866d83', 'tom.jones@gmail.com', 'customer');
INSERT INTO shop_users (username, password, email, role) VALUES ('amy.park', '8b824b943f5c11fbaefdb842475929ab4bba1882ea8bee461c75e26d3563b906', 'amy.park@gmail.com', 'customer');
INSERT INTO products (name, description, price, category, stock, sku) VALUES ('Oak Bear Cub', 'Hand-carved oak bear figurine with beeswax finish. Each one unique. Ages 3+.', 38.00, 'figurines', 45, 'PPT-FIG-001');
INSERT INTO products (name, description, price, category, stock, sku) VALUES ('Felt Fox Family', 'Set of 3 hand-stitched wool felt foxes with embroidered faces. Ages 3+.', 52.00, 'plush', 60, 'PPT-PLU-002');
INSERT INTO products (name, description, price, category, stock, sku) VALUES ('Little Builder Toolkit', 'Wooden hammer, screwdriver, and 30 pegs in a canvas roll. Ages 4+.', 44.99, 'educational', 80, 'PPT-EDU-003');
INSERT INTO products (name, description, price, category, stock, sku) VALUES ('Cloud Lamb Pillow', 'Organic cotton plush lamb. Machine washable. 14 inches.', 28.00, 'plush', 120, 'PPT-PLU-004');
INSERT INTO products (name, description, price, category, stock, sku) VALUES ('Stacking Stones Set', 'Painted birch stacking pieces in a linen bag. Set of 12. Ages 2+.', 34.99, 'educational', 95, 'PPT-EDU-005');
INSERT INTO products (name, description, price, category, stock, sku) VALUES ('Puppet Theater Kit', 'Tabletop theater with 4 finger puppets and a storybook. Ages 4+.', 62.00, 'creative', 35, 'PPT-CRE-006');
INSERT INTO products (name, description, price, category, stock, sku) VALUES ('Wooden Train Set', 'Beech wood locomotive with 3 carriages and track pieces. Ages 3+.', 48.00, 'vehicles', 70, 'PPT-VEH-007');
INSERT INTO products (name, description, price, category, stock, sku) VALUES ('Rainbow Abacus', 'Maple frame abacus with 100 painted wooden beads. Ages 2+.', 26.00, 'educational', 110, 'PPT-EDU-008');
INSERT INTO orders (user_id, product_id, quantity, total, status, shipping_address) VALUES (3, 1, 2, 76.00, 'shipped', '142 Elm Street, Burlington, VT 05401');
INSERT INTO orders (user_id, product_id, quantity, total, status, shipping_address) VALUES (3, 4, 1, 28.00, 'delivered', '142 Elm Street, Burlington, VT 05401');
INSERT INTO orders (user_id, product_id, quantity, total, status, shipping_address) VALUES (4, 2, 1, 52.00, 'pending', '88 Oak Lane, Portland, ME 04101');
INSERT INTO orders (user_id, product_id, quantity, total, status, shipping_address) VALUES (5, 7, 1, 48.00, 'shipped', '305 Pine Road, Savannah, GA 31401');
INSERT INTO orders (user_id, product_id, quantity, total, status, shipping_address) VALUES (4, 5, 2, 69.98, 'delivered', '88 Oak Lane, Portland, ME 04101');
INSERT INTO orders (user_id, product_id, quantity, total, status, shipping_address) VALUES (6, 3, 1, 44.99, 'shipped', '12 Birch Ave, Asheville, NC 28801');
INSERT INTO orders (user_id, product_id, quantity, total, status, shipping_address) VALUES (7, 6, 1, 62.00, 'pending', '77 Cedar Blvd, Austin, TX 78701');
INSERT INTO orders (user_id, product_id, quantity, total, status, shipping_address) VALUES (3, 8, 3, 78.00, 'processing', '142 Elm Street, Burlington, VT 05401');
INSERT INTO orders (user_id, product_id, quantity, total, status, shipping_address) VALUES (6, 1, 1, 38.00, 'delivered', '12 Birch Ave, Asheville, NC 28801');
INSERT INTO orders (user_id, product_id, quantity, total, status, shipping_address) VALUES (5, 3, 2, 89.98, 'pending', '305 Pine Road, Savannah, GA 31401');
INSERT INTO orders (user_id, product_id, quantity, total, status, shipping_address) VALUES (7, 4, 2, 56.00, 'shipped', '77 Cedar Blvd, Austin, TX 78701');
INSERT INTO orders (user_id, product_id, quantity, total, status, shipping_address) VALUES (4, 8, 1, 26.00, 'delivered', '88 Oak Lane, Portland, ME 04101');

-- ===== crm_db =====
USE crm_db;
CREATE TABLE crm_users (id INT PRIMARY KEY AUTO_INCREMENT, username VARCHAR(50) UNIQUE NOT NULL, password VARCHAR(255) NOT NULL, full_name VARCHAR(100), role VARCHAR(20) DEFAULT 'guest', department VARCHAR(50), created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE employees (id INT PRIMARY KEY AUTO_INCREMENT, crm_user_id INT, full_name VARCHAR(100), email VARCHAR(100), department VARCHAR(50), job_description TEXT, salary DECIMAL(10,2), hire_date DATE, notes TEXT, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP);
CREATE TABLE contacts (id INT PRIMARY KEY AUTO_INCREMENT, name VARCHAR(100), email VARCHAR(100), company VARCHAR(100), phone VARCHAR(20), status VARCHAR(20) DEFAULT 'lead', assigned_to INT, notes TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);

INSERT INTO crm_users (username, password, full_name, role, department) VALUES ('guest', '4b02e0c6135a5924521217d4b679493c2a717aa57fcb56760d51f7b2aea7abda', 'Guest Account', 'guest', 'general');
INSERT INTO crm_users (username, password, full_name, role, department) VALUES ('j.martinez', '611665d3be7f6be5e6227c128f9500424b9a4fcfd092b555d3b6586491002b3f', 'Julia Martinez', 'manager', 'operations');
INSERT INTO crm_users (username, password, full_name, role, department) VALUES ('r.kim', '7fa01662bc16de3b94de83f187f17e78984922cc090c0250521e3746a4636f52', 'Rachel Kim', 'agent', 'sales');
INSERT INTO crm_users (username, password, full_name, role, department) VALUES ('d.thompson', 'b511a2d5eaca933902d8a924dca3777626de9555476ef80a6b34d30e21bd0d3a', 'Derek Thompson', 'agent', 'support');
INSERT INTO employees (crm_user_id, full_name, email, department, job_description, salary, hire_date, notes) VALUES (2, 'Julia Martinez', 'j.martinez@poppet.local', 'operations', 'Operations Manager overseeing small-batch production runs, material sourcing, and wholesale fulfillment.', 78000.00, '2018-03-15', 'Payroll access: username j.martinez / password PayCycle#88');
INSERT INTO employees (crm_user_id, full_name, email, department, job_description, salary, hire_date, notes) VALUES (3, 'Rachel Kim', 'r.kim@poppet.local', 'sales', 'Wholesale Account Manager handling boutique retailer partnerships and trade show coordination.', 65000.00, '2019-07-22', NULL);
INSERT INTO employees (crm_user_id, full_name, email, department, job_description, salary, hire_date, notes) VALUES (4, 'Derek Thompson', 'd.thompson@poppet.local', 'support', 'Customer Experience Lead managing product inquiries, returns, and artisan quality feedback.', 58000.00, '2020-01-10', NULL);
INSERT INTO employees (crm_user_id, full_name, email, department, job_description, salary, hire_date, notes) VALUES (NULL, 'Carlos Rivera', 'c.rivera@poppet.local', 'engineering', 'Senior Software Engineer maintaining the storefront, design studio, and internal tooling.', 92000.00, '2017-06-01', NULL);
INSERT INTO employees (crm_user_id, full_name, email, department, job_description, salary, hire_date, notes) VALUES (NULL, 'Aisha Patel', 'a.patel@poppet.local', 'design', 'Lead Product Designer creating new figurine concepts, packaging illustrations, and brand artwork.', 71000.00, '2019-11-18', NULL);
INSERT INTO contacts (name, email, company, phone, status, assigned_to, notes) VALUES ('Tom Bradley', 'tom@littlewonders.co', 'Little Wonders', '555-0101', 'active', 3, 'Boutique chain in Vermont. Reorders every quarter.');
INSERT INTO contacts (name, email, company, phone, status, assigned_to, notes) VALUES ('Lisa Ng', 'lisa@cubbyhole.com', 'Cubbyhole Toys', '555-0102', 'active', 3, 'Indie toy shop in Brooklyn. Loves the figurine line.');
INSERT INTO contacts (name, email, company, phone, status, assigned_to, notes) VALUES ('James Okoro', 'james@seedling.co', 'Seedling Kids', '555-0103', 'lead', 4, 'Online retailer interested in exclusive educational kits.');
INSERT INTO contacts (name, email, company, phone, status, assigned_to, notes) VALUES ('Maria Santos', 'maria@thelittleapt.com', 'The Little Apartment', '555-0104', 'active', 3, 'Gift shop in Portland. Steady plush orders.');
INSERT INTO contacts (name, email, company, phone, status, assigned_to, notes) VALUES ('Ben Harper', 'ben@parkbench.toys', 'Park Bench Toys', '555-0105', 'inactive', 4, 'Account paused. Disputed a damaged shipment in Q2.');

-- CRM additional tables (pipeline, tasks, cases, activity)
CREATE TABLE deals (
  id INT PRIMARY KEY AUTO_INCREMENT, contact_id INT, title VARCHAR(200),
  value DECIMAL(10,2), stage VARCHAR(30) DEFAULT 'inquiry',
  assigned_to INT, notes TEXT, expected_close DATE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (contact_id) REFERENCES contacts(id),
  FOREIGN KEY (assigned_to) REFERENCES crm_users(id)
);
CREATE TABLE tasks (
  id INT PRIMARY KEY AUTO_INCREMENT, title VARCHAR(200), description TEXT,
  assigned_to INT, contact_id INT, deal_id INT,
  due_date DATE, status VARCHAR(20) DEFAULT 'open', priority VARCHAR(10) DEFAULT 'medium',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (assigned_to) REFERENCES crm_users(id)
);
CREATE TABLE cases (
  id INT PRIMARY KEY AUTO_INCREMENT, contact_id INT,
  subject VARCHAR(200), description TEXT,
  status VARCHAR(20) DEFAULT 'open', priority VARCHAR(10) DEFAULT 'medium',
  assigned_to INT, resolution TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (contact_id) REFERENCES contacts(id),
  FOREIGN KEY (assigned_to) REFERENCES crm_users(id)
);
CREATE TABLE activity_log (
  id INT PRIMARY KEY AUTO_INCREMENT, user_id INT, username VARCHAR(50),
  action VARCHAR(50), entity_type VARCHAR(30), entity_id INT,
  detail TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Seed deals
INSERT INTO deals (contact_id, title, value, stage, assigned_to, notes, expected_close) VALUES
(1, 'Little Wonders Q1 Reorder', 4200.00, 'proposal', 3, 'Quarterly figurine restock. Wants 20% more Bear Cubs this round.', '2025-01-15'),
(2, 'Cubbyhole Holiday Bundle', 2800.00, 'negotiation', 3, 'Custom gift sets for holiday season. Needs branded packaging.', '2024-12-20'),
(3, 'Seedling Educational Kits Pilot', 6500.00, 'inquiry', 4, 'Initial interest in educational product line. Requested samples.', '2025-02-28'),
(4, 'Little Apartment Spring Collection', 1800.00, 'won', 3, 'Plush animal spring refresh. PO received Nov 30.', '2024-11-30'),
(1, 'Little Wonders Exclusive Line', 12000.00, 'proposal', 3, 'Custom-engraved figurines with store branding. High margin.', '2025-03-01'),
(5, 'Park Bench Account Recovery', 800.00, 'lost', 4, 'Attempted reactivation after Q2 dispute. Client not interested.', '2024-10-15');

-- Seed tasks
INSERT INTO tasks (title, description, assigned_to, contact_id, deal_id, due_date, status, priority) VALUES
('Send Q1 catalog to Little Wonders', 'Tom requested updated pricing for figurine line.', 3, 1, 1, '2024-12-10', 'open', 'high'),
('Follow up on Seedling samples', 'Shipped educational kit samples Nov 28. Check delivery.', 4, 3, 3, '2024-12-08', 'open', 'medium'),
('Prepare holiday bundle mockups', 'Lisa wants to see packaging concepts before signing.', 3, 2, 2, '2024-12-06', 'completed', 'high'),
('Call Park Bench re: account', 'Final attempt to reactivate after dispute resolution.', 4, 5, 6, '2024-11-20', 'completed', 'low'),
('Update Cubbyhole contact info', 'Lisa mentioned new warehouse address for shipping.', 3, 2, NULL, '2024-12-12', 'open', 'low'),
('Prepare NY Toy Fair materials', 'Booth registration confirmed. Need collateral by Jan 5.', 3, NULL, NULL, '2025-01-05', 'open', 'high'),
('Review returned figurine QC report', 'Quality issue flagged on batch PPT-FIG-003. Review with design.', 4, NULL, NULL, '2024-12-15', 'open', 'medium');

-- Seed cases
INSERT INTO cases (contact_id, subject, description, status, priority, assigned_to, resolution) VALUES
(5, 'Damaged shipment — order #892', 'Ben reported 3 figurines arrived with chipped paint. Sent photos via email. Requesting replacement or refund.', 'resolved', 'high', 4, 'Replacement shipment sent Dec 1. Root cause: insufficient padding in shipping box. Updated packaging SOP.'),
(1, 'Invoice discrepancy Q3', 'Tom flagged a $120 difference between PO and invoice on Sept order. Need accounting to reconcile.', 'resolved', 'medium', 3, 'Identified duplicate shipping charge. Credit memo issued.'),
(2, 'Custom packaging timeline', 'Lisa asking about lead time for branded gift box printing. Need quote from vendor.', 'open', 'medium', 3, NULL),
(3, 'Sample kit missing components', 'James received educational kit sample but the counting beads set was missing from the package.', 'open', 'high', 4, NULL),
(4, 'Bulk pricing inquiry', 'Maria wants to know if volume discounts apply to orders over 200 units. Check with ops.', 'open', 'low', 3, NULL);

-- Seed activity log
INSERT INTO activity_log (user_id, username, action, entity_type, entity_id, detail, created_at) VALUES
(3, 'r.kim', 'created', 'deal', 1, 'Created deal: Little Wonders Q1 Reorder ($4,200)', '2024-11-28 09:14:00'),
(3, 'r.kim', 'updated', 'deal', 2, 'Moved Cubbyhole Holiday Bundle to Negotiation stage', '2024-11-29 14:30:00'),
(4, 'd.thompson', 'created', 'case', 4, 'Opened case: Sample kit missing components', '2024-12-02 10:45:00'),
(3, 'r.kim', 'updated', 'contact', 1, 'Updated Tom Bradley phone number', '2024-12-03 11:20:00'),
(4, 'd.thompson', 'resolved', 'case', 1, 'Resolved: Damaged shipment — replacement sent', '2024-12-01 16:00:00'),
(2, 'j.martinez', 'updated', 'employee', 3, 'Updated Rachel Kim job description', '2024-12-04 08:30:00'),
(3, 'r.kim', 'created', 'task', 6, 'Created task: Prepare NY Toy Fair materials', '2024-12-04 09:00:00'),
(3, 'r.kim', 'won', 'deal', 4, 'Deal won: Little Apartment Spring Collection ($1,800)', '2024-11-30 15:45:00'),
(4, 'd.thompson', 'created', 'case', 3, 'Opened case: Custom packaging timeline inquiry', '2024-12-03 14:15:00'),
(3, 'r.kim', 'created', 'deal', 5, 'Created deal: Little Wonders Exclusive Line ($12,000)', '2024-12-05 10:00:00');

-- ===== payroll_db =====
USE payroll_db;
CREATE TABLE payroll_users (id INT PRIMARY KEY AUTO_INCREMENT, username VARCHAR(50) UNIQUE NOT NULL, password VARCHAR(255) NOT NULL, employee_id INT, role VARCHAR(20) DEFAULT 'viewer', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE pay_runs (id INT PRIMARY KEY AUTO_INCREMENT, period_start DATE, period_end DATE, run_date DATE, status VARCHAR(20) DEFAULT 'completed', total_gross DECIMAL(12,2), total_net DECIMAL(12,2), total_tax DECIMAL(12,2), total_deductions DECIMAL(12,2), employee_count INT, notes TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE pay_stubs (id INT PRIMARY KEY AUTO_INCREMENT, pay_run_id INT, employee_id INT, employee_name VARCHAR(100), department VARCHAR(50), gross_pay DECIMAL(10,2), federal_tax DECIMAL(10,2), state_tax DECIMAL(10,2), social_security DECIMAL(10,2), medicare DECIMAL(10,2), health_insurance DECIMAL(10,2), retirement_401k DECIMAL(10,2), net_pay DECIMAL(10,2), FOREIGN KEY (pay_run_id) REFERENCES pay_runs(id));
CREATE TABLE deductions (id INT PRIMARY KEY AUTO_INCREMENT, name VARCHAR(100), category VARCHAR(30), rate DECIMAL(6,4), is_percentage TINYINT DEFAULT 1, applies_to VARCHAR(20) DEFAULT 'all', active TINYINT DEFAULT 1);
CREATE TABLE time_off (id INT PRIMARY KEY AUTO_INCREMENT, employee_id INT, employee_name VARCHAR(100), type VARCHAR(20), start_date DATE, end_date DATE, days_count INT, status VARCHAR(20) DEFAULT 'pending', notes TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);

INSERT INTO payroll_users (username, password, employee_id, role) VALUES ('j.martinez', 'PayCycle#88', 1, 'viewer');
INSERT INTO payroll_users (username, password, employee_id, role) VALUES ('payroll_admin', 'AdminPR2024!Secure', NULL, 'admin');

-- Deduction templates
INSERT INTO deductions (name, category, rate, is_percentage, applies_to) VALUES ('Federal Income Tax', 'tax', 0.2200, 1, 'all');
INSERT INTO deductions (name, category, rate, is_percentage, applies_to) VALUES ('NC State Tax', 'tax', 0.0525, 1, 'all');
INSERT INTO deductions (name, category, rate, is_percentage, applies_to) VALUES ('Social Security (FICA)', 'tax', 0.0620, 1, 'all');
INSERT INTO deductions (name, category, rate, is_percentage, applies_to) VALUES ('Medicare', 'tax', 0.0145, 1, 'all');
INSERT INTO deductions (name, category, rate, is_percentage, applies_to) VALUES ('Health Insurance (PPO)', 'benefit', 0.0000, 0, 'enrolled');
INSERT INTO deductions (name, category, rate, is_percentage, applies_to) VALUES ('401(k) Contribution', 'retirement', 0.0600, 1, 'enrolled');
INSERT INTO deductions (name, category, rate, is_percentage, applies_to) VALUES ('Dental Insurance', 'benefit', 0.0000, 0, 'enrolled');

-- Pay runs (last 4 months)
INSERT INTO pay_runs (period_start, period_end, run_date, status, total_gross, total_net, total_tax, total_deductions, employee_count, notes) VALUES ('2024-12-01', '2024-12-31', '2024-12-31', 'processing', 30333.33, 21536.67, 6666.67, 2130.00, 5, 'December payroll in progress');
INSERT INTO pay_runs (period_start, period_end, run_date, status, total_gross, total_net, total_tax, total_deductions, employee_count, notes) VALUES ('2024-11-01', '2024-11-30', '2024-11-29', 'completed', 30333.33, 21536.67, 6666.67, 2130.00, 5, NULL);
INSERT INTO pay_runs (period_start, period_end, run_date, status, total_gross, total_net, total_tax, total_deductions, employee_count, notes) VALUES ('2024-10-01', '2024-10-31', '2024-10-31', 'completed', 30333.33, 21536.67, 6666.67, 2130.00, 5, NULL);
INSERT INTO pay_runs (period_start, period_end, run_date, status, total_gross, total_net, total_tax, total_deductions, employee_count, notes) VALUES ('2024-09-01', '2024-09-30', '2024-09-30', 'completed', 30333.33, 21536.67, 6666.67, 2130.00, 5, NULL);

-- Pay stubs for November
INSERT INTO pay_stubs (pay_run_id, employee_id, employee_name, department, gross_pay, federal_tax, state_tax, social_security, medicare, health_insurance, retirement_401k, net_pay) VALUES (2, 1, 'Julia Martinez', 'operations', 6500.00, 1430.00, 341.25, 403.00, 94.25, 285.00, 390.00, 3556.50);
INSERT INTO pay_stubs (pay_run_id, employee_id, employee_name, department, gross_pay, federal_tax, state_tax, social_security, medicare, health_insurance, retirement_401k, net_pay) VALUES (2, 2, 'Rachel Kim', 'sales', 5416.67, 1191.67, 284.38, 335.83, 78.54, 285.00, 325.00, 2916.25);
INSERT INTO pay_stubs (pay_run_id, employee_id, employee_name, department, gross_pay, federal_tax, state_tax, social_security, medicare, health_insurance, retirement_401k, net_pay) VALUES (2, 3, 'Derek Thompson', 'support', 4833.33, 1063.33, 253.75, 299.67, 70.08, 285.00, 290.00, 2571.50);
INSERT INTO pay_stubs (pay_run_id, employee_id, employee_name, department, gross_pay, federal_tax, state_tax, social_security, medicare, health_insurance, retirement_401k, net_pay) VALUES (2, 4, 'Carlos Rivera', 'engineering', 7666.67, 1686.67, 402.50, 475.33, 111.17, 285.00, 460.00, 4246.00);
INSERT INTO pay_stubs (pay_run_id, employee_id, employee_name, department, gross_pay, federal_tax, state_tax, social_security, medicare, health_insurance, retirement_401k, net_pay) VALUES (2, 5, 'Aisha Patel', 'design', 5916.67, 1301.67, 310.63, 366.83, 85.79, 285.00, 355.00, 3212.75);

-- Time off requests
INSERT INTO time_off (employee_id, employee_name, type, start_date, end_date, days_count, status, notes) VALUES (2, 'Rachel Kim', 'vacation', '2024-12-23', '2024-12-27', 3, 'approved', 'Holiday break');
INSERT INTO time_off (employee_id, employee_name, type, start_date, end_date, days_count, status, notes) VALUES (4, 'Carlos Rivera', 'sick', '2024-12-09', '2024-12-09', 1, 'approved', NULL);
INSERT INTO time_off (employee_id, employee_name, type, start_date, end_date, days_count, status, notes) VALUES (3, 'Derek Thompson', 'vacation', '2025-01-02', '2025-01-03', 2, 'pending', 'New Year extended');
INSERT INTO time_off (employee_id, employee_name, type, start_date, end_date, days_count, status, notes) VALUES (1, 'Julia Martinez', 'personal', '2024-11-15', '2024-11-15', 1, 'approved', 'Appointment');
INSERT INTO time_off (employee_id, employee_name, type, start_date, end_date, days_count, status, notes) VALUES (5, 'Aisha Patel', 'vacation', '2024-12-30', '2025-01-03', 3, 'pending', 'Year-end break');

-- ===== dispatch_db =====
USE dispatch_db;
CREATE TABLE carriers (id INT PRIMARY KEY AUTO_INCREMENT, name VARCHAR(50), code VARCHAR(20) UNIQUE, tracking_url_template VARCHAR(200), active TINYINT DEFAULT 1);
CREATE TABLE shipments (id INT PRIMARY KEY AUTO_INCREMENT, order_id INT, carrier_id INT, tracking_number VARCHAR(50), status VARCHAR(20) DEFAULT 'pending', weight_grams INT, ship_date DATETIME, delivered_date DATETIME, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);

INSERT INTO carriers (name, code, tracking_url_template, active) VALUES ('USPS', 'usps', 'https://tools.usps.com/go/TrackConfirmAction?tLabels={tracking}', 1);
INSERT INTO carriers (name, code, tracking_url_template, active) VALUES ('UPS', 'ups', 'https://www.ups.com/track?tracknum={tracking}', 1);
INSERT INTO carriers (name, code, tracking_url_template, active) VALUES ('FedEx', 'fedex', 'https://www.fedex.com/fedextrack/?trknbr={tracking}', 1);
INSERT INTO carriers (name, code, tracking_url_template, active) VALUES ('DHL', 'dhl', 'https://www.dhl.com/en/express/tracking.html?AWB={tracking}', 0);
INSERT INTO shipments (order_id, carrier_id, tracking_number, status, weight_grams, ship_date, delivered_date) VALUES (1, 1, '9400111899223100001234', 'in_transit', 680, '2024-12-01 10:30:00', NULL);
INSERT INTO shipments (order_id, carrier_id, tracking_number, status, weight_grams, ship_date, delivered_date) VALUES (2, 2, '1Z999AA10123456784', 'delivered', 340, '2024-11-20 09:15:00', '2024-11-24 14:22:00');
INSERT INTO shipments (order_id, carrier_id, tracking_number, status, weight_grams, ship_date, delivered_date) VALUES (4, 1, '9400111899223100005678', 'in_transit', 520, '2024-12-02 11:00:00', NULL);
INSERT INTO shipments (order_id, carrier_id, tracking_number, status, weight_grams, ship_date, delivered_date) VALUES (5, 3, '794644790128', 'delivered', 410, '2024-11-18 08:45:00', '2024-11-22 16:30:00');
INSERT INTO shipments (order_id, carrier_id, tracking_number, status, weight_grams, ship_date, delivered_date) VALUES (6, 2, '1Z999BB10987654321', 'in_transit', 290, '2024-12-03 14:20:00', NULL);
INSERT INTO shipments (order_id, carrier_id, tracking_number, status, weight_grams, ship_date, delivered_date) VALUES (9, 1, '9400111899223100009012', 'delivered', 680, '2024-11-15 09:00:00', '2024-11-19 11:45:00');
INSERT INTO shipments (order_id, carrier_id, tracking_number, status, weight_grams, ship_date, delivered_date) VALUES (11, 3, '794644790256', 'in_transit', 450, '2024-12-04 10:10:00', NULL);
INSERT INTO shipments (order_id, carrier_id, tracking_number, status, weight_grams, ship_date, delivered_date) VALUES (12, 2, '1Z999CC10111213141', 'delivered', 200, '2024-11-25 13:30:00', '2024-11-29 10:15:00');