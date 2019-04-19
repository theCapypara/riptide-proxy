pipeline {
    agent any
    options {
        disableConcurrentBuilds()
    }

    stages {

        stage('Build') {
            steps {
                // Setup virtual env
                sh "rm -rf .venv || true"
                sh "virtualenv .venv"
                sh ". .venv/bin/activate"

                // Run build
                sh "rm -rf dist build || true"
                sh "pip3 install -r requirements.txt"
                sh "python3 setup.py bdist_wheel"
            }
            post {
                always {
                    archiveArtifacts allowEmptyArchive: true, artifacts: 'dist/*whl', fingerprint: true
                }
            }
        }

        stage('Deploy to PyPI') {
            when {
                branch "release"
            }
            environment {
                TWINE    = credentials('parakoopa-twine-username-password')
            }
            steps {
                sh 'twine -u "$TWINE_USR" -p "$TWINE_PSW" upload dist/*'
            }
        }

    }

}