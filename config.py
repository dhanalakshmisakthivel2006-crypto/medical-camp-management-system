import os

class Config:
    SECRET_KEY = "medicalcamp123"
    SQLALCHEMY_DATABASE_URI = "sqlite:///patients.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    BOOTSTRAP_SERVE_LOCAL = True

