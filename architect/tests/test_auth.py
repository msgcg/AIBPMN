import json
from django.test import TestCase, Client
from django.contrib.auth.models import User
from architect.models import Project, KnowledgeBaseFile
from architect.views import validate_username_and_password


class AuthValidationTests(TestCase):
    def test_valid_credentials(self):
        valid, err = validate_username_and_password(
            username="alex_bpm",
            password="SecurePassword123!",
            password_confirm="SecurePassword123!",
            is_registration=True
        )
        self.assertTrue(valid)
        self.assertEqual(err, "")

    def test_reject_cyrillic_username(self):
        valid, err = validate_username_and_password(
            username="пользователь",
            password="SecurePassword123!",
            password_confirm="SecurePassword123!",
            is_registration=True
        )
        self.assertFalse(valid)
        self.assertIn("только английские", err)

    def test_reject_cyrillic_password(self):
        valid, err = validate_username_and_password(
            username="valid_user",
            password="СложныйПароль123!",
            password_confirm="СложныйПароль123!",
            is_registration=True
        )
        self.assertFalse(valid)
        self.assertIn("английских символов", err)

    def test_reject_short_username(self):
        valid, err = validate_username_and_password(
            username="ab",
            password="SecurePassword123!",
            password_confirm="SecurePassword123!",
            is_registration=True
        )
        self.assertFalse(valid)
        self.assertIn("от 3 до 30", err)

    def test_reject_password_missing_uppercase(self):
        valid, err = validate_username_and_password(
            username="valid_user",
            password="securepassword123!",
            password_confirm="securepassword123!",
            is_registration=True
        )
        self.assertFalse(valid)
        self.assertIn("заглавную", err)

    def test_reject_password_missing_digit(self):
        valid, err = validate_username_and_password(
            username="valid_user",
            password="SecurePassword!",
            password_confirm="SecurePassword!",
            is_registration=True
        )
        self.assertFalse(valid)
        self.assertIn("цифру", err)

    def test_reject_password_missing_special_char(self):
        valid, err = validate_username_and_password(
            username="valid_user",
            password="SecurePassword123",
            password_confirm="SecurePassword123",
            is_registration=True
        )
        self.assertFalse(valid)
        self.assertIn("специальный символ", err)

    def test_reject_password_containing_username(self):
        valid, err = validate_username_and_password(
            username="john_doe",
            password="Super_john_doe_999!",
            password_confirm="Super_john_doe_999!",
            is_registration=True
        )
        self.assertFalse(valid)
        self.assertIn("не должен содержать в себе логин", err)

    def test_reject_password_confirm_mismatch(self):
        valid, err = validate_username_and_password(
            username="valid_user",
            password="SecurePassword123!",
            password_confirm="DifferentPassword123!",
            is_registration=True
        )
        self.assertFalse(valid)
        self.assertIn("не совпадают", err)


class AuthApiTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_register_api_success(self):
        resp = self.client.post(
            '/api/auth/register/',
            data=json.dumps({
                'username': 'john_bpm',
                'password': 'StrongPass123!@#',
                'password_confirm': 'StrongPass123!@#'
            }),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['user']['username'], 'john_bpm')

        # Check user created in database
        user = User.objects.get(username='john_bpm')
        self.assertIsNotNone(user)

        # Check starter project was created for user
        user_proj = Project.objects.filter(user=user).first()
        self.assertIsNotNone(user_proj)
        self.assertEqual(user_proj.diagrams.count(), 1)

        # Check user knowledge base was seeded in DB
        kb_files = KnowledgeBaseFile.objects.filter(user=user)
        self.assertGreater(kb_files.count(), 0)

    def test_register_duplicate_username(self):
        User.objects.create_user(username='existing_user', password='Password123!')
        resp = self.client.post(
            '/api/auth/register/',
            data=json.dumps({
                'username': 'existing_user',
                'password': 'StrongPass123!@#',
                'password_confirm': 'StrongPass123!@#'
            }),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data['success'])
        self.assertIn("уже существует", data['error'])

    def test_login_and_logout_flow(self):
        # Register user
        user = User.objects.create_user(username='login_user', password='StrongPass123!@#')
        
        # Login with correct password
        resp = self.client.post(
            '/api/auth/login/',
            data=json.dumps({
                'username': 'login_user',
                'password': 'StrongPass123!@#'
            }),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])

        # Check auth/me
        resp_me = self.client.get('/api/auth/me/')
        self.assertEqual(resp_me.status_code, 200)
        self.assertTrue(resp_me.json()['authenticated'])
        self.assertEqual(resp_me.json()['username'], 'login_user')

        # Logout
        resp_logout = self.client.post('/api/auth/logout/')
        self.assertEqual(resp_logout.status_code, 200)
        self.assertTrue(resp_logout.json()['success'])

        # Verify no longer authenticated
        resp_me2 = self.client.get('/api/auth/me/')
        self.assertFalse(resp_me2.json()['authenticated'])

    def test_change_password_unauthenticated(self):
        resp = self.client.post(
            '/api/auth/change-password/',
            data=json.dumps({
                'old_password': 'SomePassword123!',
                'new_password': 'NewPassword123!@#',
                'new_password_confirm': 'NewPassword123!@#'
            }),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 401)

    def test_change_password_wrong_old_password(self):
        user = User.objects.create_user(username='pwd_user', password='InitialPass123!@#')
        self.client.force_login(user)

        resp = self.client.post(
            '/api/auth/change-password/',
            data=json.dumps({
                'old_password': 'WrongOldPassword123!',
                'new_password': 'NewPassword123!@#',
                'new_password_confirm': 'NewPassword123!@#'
            }),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Неверный текущий пароль", resp.json()['error'])

    def test_change_password_weak_new_password(self):
        user = User.objects.create_user(username='pwd_user2', password='InitialPass123!@#')
        self.client.force_login(user)

        resp = self.client.post(
            '/api/auth/change-password/',
            data=json.dumps({
                'old_password': 'InitialPass123!@#',
                'new_password': 'weak',
                'new_password_confirm': 'weak'
            }),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("не менее 8 символов", resp.json()['error'])

    def test_change_password_contains_username(self):
        user = User.objects.create_user(username='alex_bpm', password='InitialPass123!@#')
        self.client.force_login(user)

        resp = self.client.post(
            '/api/auth/change-password/',
            data=json.dumps({
                'old_password': 'InitialPass123!@#',
                'new_password': 'alex_bpm_Strong123!@#',
                'new_password_confirm': 'alex_bpm_Strong123!@#'
            }),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("содержать в себе логин", resp.json()['error'])

    def test_change_password_mismatch_confirm(self):
        user = User.objects.create_user(username='pwd_user3', password='InitialPass123!@#')
        self.client.force_login(user)

        resp = self.client.post(
            '/api/auth/change-password/',
            data=json.dumps({
                'old_password': 'InitialPass123!@#',
                'new_password': 'NewStrongPassword123!@#',
                'new_password_confirm': 'DifferentPassword123!@#'
            }),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("не совпадают", resp.json()['error'])

    def test_change_password_same_as_old(self):
        user = User.objects.create_user(username='pwd_user4', password='InitialPass123!@#')
        self.client.force_login(user)

        resp = self.client.post(
            '/api/auth/change-password/',
            data=json.dumps({
                'old_password': 'InitialPass123!@#',
                'new_password': 'InitialPass123!@#',
                'new_password_confirm': 'InitialPass123!@#'
            }),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("должен отличаться", resp.json()['error'])

    def test_change_password_success(self):
        user = User.objects.create_user(username='change_pwd_ok', password='InitialPass123!@#')
        self.client.force_login(user)

        resp = self.client.post(
            '/api/auth/change-password/',
            data=json.dumps({
                'old_password': 'InitialPass123!@#',
                'new_password': 'BrandNewPass456!@#',
                'new_password_confirm': 'BrandNewPass456!@#'
            }),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])

        # Check that user can log in with new password
        user.refresh_from_db()
        self.assertTrue(user.check_password('BrandNewPass456!@#'))
        self.assertFalse(user.check_password('InitialPass123!@#'))

    def test_delete_account_unauthenticated(self):
        resp = self.client.post(
            '/api/auth/delete-account/',
            data=json.dumps({'password': 'SomePassword123!'}),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 401)

    def test_delete_account_wrong_password(self):
        user = User.objects.create_user(username='del_user_fail', password='StrongPass123!@#')
        self.client.force_login(user)

        resp = self.client.post(
            '/api/auth/delete-account/',
            data=json.dumps({'password': 'WrongPassword123!'}),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Неверный пароль", resp.json()['error'])
        # User should still exist
        self.assertTrue(User.objects.filter(username='del_user_fail').exists())

    def test_delete_account_success(self):
        user = User.objects.create_user(username='del_user_ok', password='StrongPass123!@#')
        proj = Project.objects.create(user=user, name="User Project")
        KnowledgeBaseFile.objects.create(user=user, name="user_notes.md", content_base64="VGVzdA==")
        self.client.force_login(user)

        resp = self.client.post(
            '/api/auth/delete-account/',
            data=json.dumps({'password': 'StrongPass123!@#'}),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])

        # User and all associated data should be deleted
        self.assertFalse(User.objects.filter(username='del_user_ok').exists())
        self.assertFalse(Project.objects.filter(id=proj.id).exists())
        self.assertFalse(KnowledgeBaseFile.objects.filter(user=user).exists())

        # Session should be logged out
        resp_me = self.client.get('/api/auth/me/')
        self.assertFalse(resp_me.json()['authenticated'])

