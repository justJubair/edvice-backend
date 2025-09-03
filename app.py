from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
import datetime
from datetime import UTC
import os
from functools import wraps
from bson import ObjectId
from werkzeug.utils import secure_filename
from werkzeug.exceptions import BadRequest

app = Flask(__name__)
CORS(app)

# MongoDB connection
try:
    client = MongoClient(
        "mongodb+srv://edvice:KSKZu2kJh0QtR2Gp@cluster0.i49oumq.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0",
        serverSelectionTimeoutMS=10000,  # 10 second timeout
        connectTimeoutMS=20000,  # 20 second connection timeout
        socketTimeoutMS=10000,  # 10 second socket timeout
        maxPoolSize=5,  # Smaller connection pool
        retryWrites=True,
        retryReads=True,
    )
    # Test the connection
    client.admin.command("ping")
    print("MongoDB connection successful!")
except Exception as e:
    print(f"MongoDB connection failed: {e}")
    print("Please check your internet connection and MongoDB Atlas settings.")
    # For development, you can comment out the exit to continue without MongoDB
    # import sys
    # sys.exit(1)

db = client["edvice"]
partners = db["partners"]
students = db["students"]
admins = db["admins"]
support_requests = db["support_requests"]
contact_submissions = db["contact_submissions"]

# JWT secret key
app.config["SECRET_KEY"] = os.urandom(24)

# File upload configuration
UPLOAD_FOLDER = "./uploads"
ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "doc", "docx"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# Token required decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization")
        print(token)
        if not token:
            return jsonify({"message": "Token is missing!"}), 401
        try:
            token = token.split(" ")[1]  # Remove 'Bearer ' prefix
            data = jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])
            current_partner = partners.find_one({"email": data["email"]})
            if not current_partner:
                return jsonify({"message": "Invalid token!"}), 401
        except:
            return jsonify({"message": "Invalid token!"}), 401
        return f(current_partner, *args, **kwargs)

    return decorated


# Admin token required decorator
def admin_token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization")
        print(token)
        if not token:
            return jsonify({"message": "Admin token is missing!"}), 401
        try:
            token = token.split(" ")[1]  # Remove 'Bearer ' prefix
            data = jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])
            current_admin = admins.find_one({"email": data["email"]})
            if not current_admin:
                return jsonify({"message": "Invalid admin token!"}), 401
        except:
            return jsonify({"message": "Invalid admin token!"}), 401
        return f(current_admin, *args, **kwargs)

    return decorated


# Initialize sample admin if not exists
def init_sample_admin():
    # Delete existing admin if exists
    admins.delete_one({"email": "skibidi@gmail.com"})

    # Create new admin with updated credentials
    hashed_password = generate_password_hash("edviceuk@edviceuk.com")
    admins.insert_one(
        {
            "email": "edviceuk@edviceuk.com",
            "password": hashed_password,
            "name": "Admin",
            "created_at": datetime.datetime.now(UTC),
        }
    )


# Initialize sample admin
init_sample_admin()

# Delete the sample partner if it exists
sample_partner = partners.find_one({"email": "skibidi@gmail.com"})
if sample_partner:
    # Delete all students associated with this partner
    students.delete_many({"partner_email": "skibidi@gmail.com"})
    # Delete the partner
    partners.delete_one({"email": "skibidi@gmail.com"})
    print("Sample partner account deleted successfully")


@app.route("/api/partner/login", methods=["POST"])
def login():
    data = request.get_json()
    if not data or not data.get("email") or not data.get("password"):
        return jsonify({"message": "Missing email or password"}), 400

    partner = partners.find_one({"email": data["email"]})
    if not partner or not check_password_hash(partner["password"], data["password"]):
        return jsonify({"message": "Invalid email or password"}), 401

    token = jwt.encode(
        {
            "email": partner["email"],
            "exp": datetime.datetime.now(UTC) + datetime.timedelta(days=1),
        },
        app.config["SECRET_KEY"],
    )

    return jsonify(
        {
            "token": token,
            "partner": {"email": partner["email"], "name": partner.get("name", "")},
        }
    )


@app.route("/api/partner/verify", methods=["GET"])
@token_required
def verify_token(current_partner):
    return jsonify(
        {
            "partner": {
                "email": current_partner["email"],
                "name": current_partner.get("name", ""),
            }
        }
    )

@app.get("/api/partner/profile")
@token_required
def get_partner(current_partner):
    del current_partner["_id"]
    del current_partner["password"]
    return current_partner

@app.put("/api/partner/profile")
@token_required
def update_partner_info(current_partner):
    data = request.get_json()
    partners.update_one({"_id": current_partner["_id"]}, {"$set": data})
    return jsonify({"message": "Partner info updated successfully."})

# Student Management Endpoints
@app.route("/api/students", methods=["GET"])
@token_required
def get_students(current_partner):
    student_list = list(students.find({"partner_email": current_partner["email"]}))
    # Convert ObjectId to string for JSON serialization
    for student in student_list:
        student["_id"] = str(student["_id"])
    return jsonify({"students": student_list})


@app.route("/api/students", methods=["POST"])
@token_required
def create_student(current_partner):
    data = request.get_json()

    # Generate student ID (EDV + year + 3-digit sequence)
    year = datetime.datetime.now(UTC).year
    last_student = students.find_one(
        {"student_id": {"$regex": f"EDV{year}"}}, sort=[("student_id", -1)]
    )

    if last_student:
        try:
            last_seq = int(last_student["student_id"][-3:])
            new_seq = str(last_seq + 1).zfill(3)
        except ValueError:
            # Handle cases where the sequence is not a number
            new_seq = "001"
    else:
        new_seq = "001"

    student_id = f"EDV{year}{new_seq}"

    student = {
        "student_id": student_id,
        "partner_email": current_partner["email"],
        "name": data["name"],
        "preferred_intakes": data["preferred_intakes"],
        "study_levels": data["study_levels"],
        "documents": [],  # Documents will be added via upload endpoint
        "admission_status": data.get("admission_status", "Application not started"),
        "commission_status": data.get("commission_status", "Not invoiced"),
        "shortlist_url": None,
        "created_at": datetime.datetime.now(UTC),
        "updated_at": datetime.datetime.now(UTC),
    }

    result = students.insert_one(student)
    student["_id"] = str(result.inserted_id)
    return jsonify({"student": student}), 201

@app.get("/api/students/<student_id>")
@token_required
def get_student(current_partner, student_id):
    # Verify student belongs to partner
    student = students.find_one(
        {"student_id": student_id, "partner_email": current_partner["email"]}
    )
    print(student)
    if not student:
        return jsonify({"message": "Student not found"}), 404

    student["_id"] = str(student["_id"])

    return {"student": student}


@app.route("/api/students/<student_id>", methods=["PUT"])
@token_required
def update_student(current_partner, student_id):
    data = request.get_json()

    # Verify student belongs to partner
    student = students.find_one(
        {"student_id": student_id, "partner_email": current_partner["email"]}
    )

    if not student:
        return jsonify({"message": "Student not found"}), 404

    update_data = {
        "name": data.get("name", student["name"]),
        "preferred_intakes": data.get(
            "preferred_intakes", student["preferred_intakes"]
        ),
        "study_levels": data.get("study_levels", student["study_levels"]),
        # Documents are handled by the upload endpoint
        "admission_status": data.get("admission_status", student["admission_status"]),
        "commission_status": data.get(
            "commission_status", student["commission_status"]
        ),
        "updated_at": datetime.datetime.now(UTC),
    }

    # Remove None values from update_data
    update_data = {k: v for k, v in update_data.items() if v is not None}

    if update_data:
        students.update_one({"_id": student["_id"]}, {"$set": update_data})

    updated_student = students.find_one({"_id": student["_id"]})
    updated_student["_id"] = str(updated_student["_id"])
    return jsonify({"student": updated_student})

@app.put("/api/students/<student_id>/emergency-contact")
@token_required
def update_emergency_contact(current_partner, student_id):
    try:
        data = request.get_json(force=True)
    except BadRequest:
        return jsonify({"message": "Invalid JSON format"}), 400

    required_fields = ["name", "relationship", "phone", "email"]
    missing_fields = [field for field in required_fields if field not in data or not data[field]]
    if missing_fields:
        return jsonify({"message": f"Missing fields: {', '.join(missing_fields)}"}), 400

    if not str(data["phone"]).isdigit():
        return jsonify({"message": "Phone number must contain only digits"}), 400

    student = students.find_one({
        "student_id": student_id,
        "partner_email": current_partner["email"]
    })

    if not student:
        return jsonify({"message": "Student not found or does not belong to your account"}), 404

    students.update_one({"_id": student["_id"]}, {"$set": {"emergency_contact": data}})

    return jsonify({"message": "Emergency Contact Updated Successfully."}), 200

@app.route("/api/students/<student_id>", methods=["DELETE"])
@token_required
def delete_student(current_partner, student_id):
    # In a real app, you might also want to delete the uploaded files
    result = students.delete_one(
        {"student_id": student_id, "partner_email": current_partner["email"]}
    )

    if result.deleted_count == 0:
        return jsonify({"message": "Student not found"}), 404

    return jsonify({"message": "Student deleted successfully"})


@app.post("/api/students/<student_id>/edit-shortlist-url")
@admin_token_required
def edit_url(admin, student_id):
    data = request.get_json()

    # Verify student belongs to partner
    student = students.find_one(
        {
            "student_id": student_id,
        }
    )

    if not student:
        return jsonify({"message": "Student not found"}), 404

    if not student.get("shortlist_url") == data.get("shortlist_url"):
        students.update_one(
            {"_id": student["_id"]},
            {"$set": {"shortlist_url": data.get("shortlist_url")}},
        )

    updated_student = students.find_one({"_id": student["_id"]})
    updated_student["_id"] = str(updated_student["_id"])
    return jsonify({"student": updated_student})


@app.route("/api/students/<student_id>/documents", methods=["POST"])
@token_required
def upload_document(current_partner, student_id):
    # Verify student belongs to partner
    student = students.find_one(
        {"student_id": student_id, "partner_email": current_partner["email"]}
    )

    if not student:
        return jsonify({"message": "Student not found"}), 404

    if "files" not in request.files:
        return jsonify({"message": "No file part in the request"}), 400

    files = request.files.getlist("files")
    uploaded_documents = []

    # Ensure the upload folder exists
    if not os.path.exists(app.config["UPLOAD_FOLDER"]):
        os.makedirs(app.config["UPLOAD_FOLDER"])

    # Create a student-specific folder if it doesn't exist
    student_upload_folder = os.path.join(app.config["UPLOAD_FOLDER"], student_id)
    if not os.path.exists(student_upload_folder):
        os.makedirs(student_upload_folder)

    for file in files:
        if file.filename == "":
            continue

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(student_upload_folder, filename)
            file.save(filepath)

            # Store document info in the student's document list
            document_info = {
                "name": filename,
                "path": filepath,  # Store the server path
                "uploaded_at": datetime.datetime.now(UTC),
            }
            students.update_one(
                {"_id": student["_id"]}, {"$push": {"documents": document_info}}
            )
            uploaded_documents.append(document_info)

    if not uploaded_documents:
        return jsonify({"message": "No valid files uploaded"}), 400

    updated_student = students.find_one({"_id": student["_id"]})
    updated_student["_id"] = str(updated_student["_id"])
    return (
        jsonify(
            {"student": updated_student, "uploaded_count": len(uploaded_documents)}
        ),
        200,
    )


@app.route("/api/students/<student_id>/documents/<filename>", methods=["GET"])
@token_required
def download_document(current_partner, student_id, filename):
    # Verify student belongs to partner
    student = students.find_one(
        {"student_id": student_id, "partner_email": current_partner["email"]}
    )

    if not student:
        return jsonify({"message": "Student not found"}), 404

    # Find the document in the student's document list
    document = next(
        (doc for doc in student.get("documents", []) if doc["name"] == filename), None
    )

    if not document:
        return jsonify({"message": "Document not found"}), 404

    # Ensure the partner can only download documents within their student's directory
    document_path = document["path"]
    student_upload_folder = os.path.join(app.config["UPLOAD_FOLDER"], student_id)

    if not document_path.startswith(student_upload_folder):
        return jsonify({"message": "Invalid document path"}), 400

    try:
        # Use safe sending of files from the directory
        return send_from_directory(student_upload_folder, filename, as_attachment=True)
    except FileNotFoundError:
        return jsonify({"message": "File not found on server"}), 404


@app.route("/api/students/<student_id>/documents/<filename>", methods=["DELETE"])
@token_required
def delete_document(current_partner, student_id, filename):
    # Verify student belongs to partner
    student = students.find_one(
        {"student_id": student_id, "partner_email": current_partner["email"]}
    )

    if not student:
        return jsonify({"message": "Student not found"}), 404

    # Find the document in the student's document list
    document_to_delete = next(
        (doc for doc in student.get("documents", []) if doc["name"] == filename), None
    )

    if not document_to_delete:
        return jsonify({"message": "Document not found"}), 404

    # Construct the expected file path and verify it's within the student's directory
    expected_filepath = os.path.join(
        app.config["UPLOAD_FOLDER"], student_id, secure_filename(filename)
    )

    if document_to_delete["path"] != expected_filepath:
        # This is a safety check in case the path in DB is malformed or malicious
        return (
            jsonify({"message": "Invalid document path in database"}),
            500,
        )  # Internal server error

    # Delete the file from the filesystem
    try:
        os.remove(expected_filepath)
    except OSError as e:
        # Log the error for server-side debugging
        print(f"Error deleting file {expected_filepath}: {e}")
        # Still remove from DB even if file deletion fails to keep DB consistent
        # In a production app, you might want a more robust cleanup mechanism

    # Remove the document from the student's document list in the database
    students.update_one(
        {"_id": student["_id"]}, {"$pull": {"documents": {"name": filename}}}
    )

    # Fetch the updated student to return
    updated_student = students.find_one({"_id": student["_id"]})
    updated_student["_id"] = str(updated_student["_id"])

    return (
        jsonify(
            {"message": "Document deleted successfully", "student": updated_student}
        ),
        200,
    )


@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    data = request.get_json()
    if not data or not data.get("email") or not data.get("password"):
        return jsonify({"message": "Missing email or password"}), 400

    admin = admins.find_one({"email": data["email"]})
    if not admin or not check_password_hash(admin["password"], data["password"]):
        return jsonify({"message": "Invalid email or password"}), 401

    token = jwt.encode(
        {
            "email": admin["email"],
            "exp": datetime.datetime.now(UTC) + datetime.timedelta(days=1),
        },
        app.config["SECRET_KEY"],
    )

    return jsonify(
        {
            "token": token,
            "admin": {"email": admin["email"], "name": admin.get("name", "")},
        }
    )


@app.route("/api/admin/verify", methods=["GET"])
@admin_token_required
def verify_admin_token(current_admin):
    return jsonify(
        {
            "admin": {
                "email": current_admin["email"],
                "name": current_admin.get("name", ""),
            }
        }
    )


@app.route("/api/admin/students", methods=["GET"])
@admin_token_required
def admin_get_students(current_admin):
    # Admin can see all students
    student_list_cursor = students.find({})
    student_list = []
    for student in student_list_cursor:
        student["_id"] = str(student["_id"])
        # Fetch partner name
        partner = partners.find_one({"email": student.get("partner_email")})
        student["partner_name"] = partner.get("name") if partner else "Unknown Partner"
        student_list.append(student)

    return jsonify({"students": student_list})


@app.route("/api/admin/students", methods=["POST"])
@admin_token_required
def admin_create_student(current_admin):
    data = request.get_json()

    # Generate student ID (EDV + year + 3-digit sequence)
    year = datetime.datetime.now(UTC).year
    last_student = students.find_one(
        {"student_id": {"$regex": f"EDV{year}"}}, sort=[("student_id", -1)]
    )

    if last_student:
        try:
            last_seq = int(last_student["student_id"][-3:])
            new_seq = str(last_seq + 1).zfill(3)
        except ValueError:
            new_seq = "001"
    else:
        new_seq = "001"

    student_id = f"EDV{year}{new_seq}"

    student = {
        "student_id": student_id,
        "partner_email": data["partner_email"],
        "name": data["name"],
        "preferred_intakes": data["preferred_intakes"],
        "study_levels": data["study_levels"],
        "documents": [],
        "admission_status": data.get("admission_status", "Application not started"),
        "commission_status": data.get("commission_status", "Not invoiced"),
        "created_at": datetime.datetime.now(UTC),
        "updated_at": datetime.datetime.now(UTC),
    }

    result = students.insert_one(student)
    student["_id"] = str(result.inserted_id)
    return jsonify({"student": student}), 201


@app.route("/api/admin/students/<student_id>", methods=["PUT"])
@admin_token_required
def admin_update_student(current_admin, student_id):
    data = request.get_json()

    # Admin can update any student
    student = students.find_one({"student_id": student_id})

    if not student:
        return jsonify({"message": "Student not found"}), 404

    update_data = {
        "name": data.get("name", student["name"]),
        "partner_email": data.get("partner_email", student["partner_email"]),
        "preferred_intakes": data.get(
            "preferred_intakes", student["preferred_intakes"]
        ),
        "study_levels": data.get("study_levels", student["study_levels"]),
        "admission_status": data.get("admission_status", student["admission_status"]),
        "commission_status": data.get(
            "commission_status", student["commission_status"]
        ),
        "updated_at": datetime.datetime.now(UTC),
    }

    # Remove None values from update_data
    update_data = {k: v for k, v in update_data.items() if v is not None}

    if update_data:
        students.update_one({"_id": student["_id"]}, {"$set": update_data})

    updated_student = students.find_one({"_id": student["_id"]})
    updated_student["_id"] = str(updated_student["_id"])
    return jsonify({"student": updated_student})


@app.route("/api/admin/students/<student_id>", methods=["DELETE"])
@admin_token_required
def admin_delete_student(current_admin, student_id):
    # Admin can delete any student
    student = students.find_one({"student_id": student_id})
    if not student:
        return jsonify({"message": "Student not found"}), 404

    # Delete associated documents from filesystem
    student_upload_folder = os.path.join(app.config["UPLOAD_FOLDER"], student_id)
    if os.path.exists(student_upload_folder):
        for filename in os.listdir(student_upload_folder):
            file_path = os.path.join(student_upload_folder, filename)
            try:
                os.remove(file_path)
            except OSError as e:
                print(f"Error deleting file {file_path}: {e}")
        try:
            os.rmdir(student_upload_folder)
        except OSError as e:
            print(f"Error deleting directory {student_upload_folder}: {e}")

    result = students.delete_one({"student_id": student_id})
    return jsonify({"message": "Student deleted successfully"})


@app.route("/api/admin/students/<student_id>/documents", methods=["POST"])
@admin_token_required
def admin_upload_document(current_admin, student_id):
    student = students.find_one({"student_id": student_id})
    if not student:
        return jsonify({"message": "Student not found"}), 404

    if "files" not in request.files:
        return jsonify({"message": "No file part in the request"}), 400

    files = request.files.getlist("files")
    uploaded_documents = []

    if not os.path.exists(app.config["UPLOAD_FOLDER"]):
        os.makedirs(app.config["UPLOAD_FOLDER"])

    student_upload_folder = os.path.join(app.config["UPLOAD_FOLDER"], student_id)
    if not os.path.exists(student_upload_folder):
        os.makedirs(student_upload_folder)

    for file in files:
        if file.filename == "":
            continue

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(student_upload_folder, filename)
            file.save(filepath)

            document_info = {
                "name": filename,
                "path": filepath,
                "uploaded_at": datetime.datetime.now(UTC),
            }
            students.update_one(
                {"_id": student["_id"]}, {"$push": {"documents": document_info}}
            )
            uploaded_documents.append(document_info)

    if not uploaded_documents:
        return jsonify({"message": "No valid files uploaded"}), 400

    updated_student = students.find_one({"_id": student["_id"]})
    updated_student["_id"] = str(updated_student["_id"])
    return (
        jsonify(
            {"student": updated_student, "uploaded_count": len(uploaded_documents)}
        ),
        200,
    )


@app.route("/api/admin/students/<student_id>/documents/<filename>", methods=["GET"])
@admin_token_required
def admin_download_document(current_admin, student_id, filename):
    student = students.find_one({"student_id": student_id})
    if not student:
        return jsonify({"message": "Student not found"}), 404

    document = next(
        (doc for doc in student.get("documents", []) if doc["name"] == filename), None
    )
    if not document:
        return jsonify({"message": "Document not found"}), 404

    document_path = document["path"]
    student_upload_folder = os.path.join(app.config["UPLOAD_FOLDER"], student_id)

    if not document_path.startswith(student_upload_folder):
        return jsonify({"message": "Invalid document path"}), 400

    try:
        return send_from_directory(student_upload_folder, filename, as_attachment=True)
    except FileNotFoundError:
        return jsonify({"message": "File not found on server"}), 404


@app.route("/api/admin/students/<student_id>/documents/<filename>", methods=["DELETE"])
@admin_token_required
def admin_delete_document(current_admin, student_id, filename):
    student = students.find_one({"student_id": student_id})
    if not student:
        return jsonify({"message": "Student not found"}), 404

    document_to_delete = next(
        (doc for doc in student.get("documents", []) if doc["name"] == filename), None
    )
    if not document_to_delete:
        return jsonify({"message": "Document not found"}), 404

    expected_filepath = os.path.join(
        app.config["UPLOAD_FOLDER"], student_id, secure_filename(filename)
    )
    if document_to_delete["path"] != expected_filepath:
        return jsonify({"message": "Invalid document path in database"}), 500

    try:
        os.remove(expected_filepath)
    except OSError as e:
        print(f"Error deleting file {expected_filepath}: {e}")

    students.update_one(
        {"_id": student["_id"]}, {"$pull": {"documents": {"name": filename}}}
    )

    updated_student = students.find_one({"_id": student["_id"]})
    updated_student["_id"] = str(updated_student["_id"])

    return (
        jsonify(
            {"message": "Document deleted successfully", "student": updated_student}
        ),
        200,
    )


@app.route("/api/support-request", methods=["POST"])
@token_required
def create_support_request(current_partner):
    data = request.get_json()
    if not data or not data.get("message"):
        return jsonify({"message": "Support message is required"}), 400

    support_request = {
        "partner_email": current_partner["email"],
        "partner_name": current_partner.get("name", ""),
        "message": data["message"],
        "status": "pending",  # pending, in_progress, resolved
        "created_at": datetime.datetime.now(UTC),
        "updated_at": datetime.datetime.now(UTC),
        "admin_notes": "",
        "resolved_at": None,
    }

    result = support_requests.insert_one(support_request)
    support_request["_id"] = str(result.inserted_id)

    return jsonify(
        {
            "message": "Support request has been submitted successfully.",
            "support_request": support_request,
        }
    )


# Admin support request endpoints
@app.route("/api/admin/support-requests", methods=["GET"])
@admin_token_required
def get_support_requests(current_admin):
    # Get all support requests, sorted by created_at in descending order
    requests = list(support_requests.find().sort("created_at", -1))
    for req in requests:
        req["_id"] = str(req["_id"])
    return jsonify({"support_requests": requests})


@app.route("/api/admin/support-requests/<request_id>", methods=["PUT"])
@admin_token_required
def update_support_request(current_admin, request_id):
    try:
        support_request = support_requests.find_one({"_id": ObjectId(request_id)})
    except:
        return jsonify({"error": "Support request not found"}), 404

    if not support_request:
        return jsonify({"error": "Support request not found"}), 404

    data = request.get_json()
    update_data = {}

    if "status" in data:
        update_data["status"] = data["status"]
        if data["status"] == "resolved":
            update_data["resolved_at"] = datetime.datetime.now(UTC)

    if "admin_notes" in data:
        update_data["admin_notes"] = data["admin_notes"]

    if update_data:
        update_data["updated_at"] = datetime.datetime.now(UTC)
        support_requests.update_one(
            {"_id": ObjectId(request_id)}, {"$set": update_data}
        )

    updated_request = support_requests.find_one({"_id": ObjectId(request_id)})
    updated_request["_id"] = str(updated_request["_id"])
    return jsonify({"support_request": updated_request})


# Partner Management Endpoints (Admin only)
@app.route("/api/admin/partners", methods=["GET"])
@admin_token_required
def get_partners(current_admin):
    partner_list = list(partners.find({}))
    # Convert ObjectId to string for JSON serialization
    for partner in partner_list:
        partner["_id"] = str(partner["_id"])
    return jsonify({"partners": partner_list})


@app.route("/api/admin/partners", methods=["POST"])
@admin_token_required
def create_partner(current_admin):
    data = request.get_json()

    if not all(k in data for k in ["name", "email", "password"]):
        return jsonify({"error": "Missing required fields"}), 400

    if partners.find_one({"email": data["email"]}):
        return jsonify({"error": "Email already registered"}), 400

    hashed_password = generate_password_hash(data["password"])
    new_partner = {
        "name": data["name"],
        "email": data["email"],
        "password": hashed_password,
        "created_at": datetime.datetime.now(UTC),
    }

    result = partners.insert_one(new_partner)
    new_partner["_id"] = str(result.inserted_id)
    # Remove password from response
    del new_partner["password"]
    return jsonify({"partner": new_partner}), 201


@app.route("/api/admin/partners/<partner_id>", methods=["PUT"])
@admin_token_required
def update_partner(current_admin, partner_id):
    try:
        partner = partners.find_one({"_id": ObjectId(partner_id)})
    except:
        return jsonify({"error": "Partner not found"}), 404

    if not partner:
        return jsonify({"error": "Partner not found"}), 404

    data = request.get_json()
    update_data = {}

    if "name" in data:
        update_data["name"] = data["name"]
    if "email" in data:
        # Check if email is already taken by another partner
        existing = partners.find_one(
            {"email": data["email"], "_id": {"$ne": ObjectId(partner_id)}}
        )
        if existing:
            return jsonify({"error": "Email already registered"}), 400
        update_data["email"] = data["email"]
    if "password" in data:
        update_data["password"] = generate_password_hash(data["password"])

    if update_data:
        try:
            partners.update_one({"_id": ObjectId(partner_id)}, {"$set": update_data})
            print(f"Partner {partner_id} updated successfully with data: {update_data}")
        except Exception as e:
            print(f"Error updating partner {partner_id}: {e}")
            return (
                jsonify({"error": f"Failed to update partner in database: {str(e)}"}),
                500,
            )

    updated_partner = partners.find_one({"_id": ObjectId(partner_id)})
    updated_partner["_id"] = str(updated_partner["_id"])
    # Remove password from response
    del updated_partner["password"]
    return jsonify({"partner": updated_partner})


@app.route("/api/admin/partners/<partner_id>", methods=["DELETE"])
@admin_token_required
def delete_partner(current_admin, partner_id):
    try:
        partner = partners.find_one({"_id": ObjectId(partner_id)})
    except:
        return jsonify({"error": "Partner not found"}), 404

    if not partner:
        return jsonify({"error": "Partner not found"}), 404

    # Delete all students associated with this partner
    students.delete_many({"partner_email": partner["email"]})

    # Delete the partner
    partners.delete_one({"_id": ObjectId(partner_id)})

    return jsonify({"message": "Partner deleted successfully"})


@app.route("/api/contact-submissions", methods=["POST"])
def receive_contact_submission():
    data = request.get_json()

    if not data or not all(
        key in data
        for key in ["firstName", "lastName", "phone", "email", "message", "country"]
    ):
        return jsonify({"message": "Missing required fields"}), 400

    # Basic validation for privacy policy agreement (optional, based on frontend)
    if "privacyPolicy" not in data or not data["privacyPolicy"]:
        return jsonify({"message": "Privacy policy agreement is required"}), 400

    submission = {
        "firstName": data["firstName"],
        "lastName": data["lastName"],
        "phone": data["phone"],
        "email": data["email"],
        "message": data["message"],
        "country": data["country"],
        "privacyPolicy": data["privacyPolicy"],
        "submitted_at": datetime.datetime.now(UTC),
    }

    try:
        result = contact_submissions.insert_one(submission)
        # Include the inserted ID in the response (optional)
        submission["_id"] = str(result.inserted_id)
        return (
            jsonify(
                {
                    "message": "Submission received successfully",
                    "submissionId": str(result.inserted_id),
                }
            ),
            201,
        )
    except Exception as e:
        print(f"Error saving contact submission: {e}")
        return jsonify({"message": "Failed to save submission"}), 500


@app.route("/api/admin/contact-submissions", methods=["GET"])
@admin_token_required
def get_contact_submissions(current_admin):
    try:
        submissions = list(contact_submissions.find().sort("submitted_at", -1))
        # Convert ObjectId to string for JSON serialization
        for submission in submissions:
            submission["_id"] = str(submission["_id"])
        return jsonify({"contact_submissions": submissions}), 200
    except Exception as e:
        print(f"Error fetching contact submissions: {e}")
        return jsonify({"message": "Failed to fetch submissions"}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
